"""Call a Murf Falcon SageMaker endpoint in each of its three modes.

    python examples/invoke.py <endpoint> realtime  --text "Hello there." --out hello.wav
    python examples/invoke.py <endpoint> stream    --text "Hello there." --out hello.mp3
    python examples/invoke.py <endpoint> bidi      --out session.pcm

``bidi`` needs ``pip install aws-sdk-sagemaker-runtime-http2`` (Python 3.12+).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time

import boto3

REGION = os.environ.get("AWS_REGION") or boto3.Session().region_name


def realtime(endpoint: str, text: str, voice: dict, out: str) -> None:
    rt = boto3.client("sagemaker-runtime", region_name=REGION)
    t0 = time.perf_counter()
    resp = rt.invoke_endpoint(EndpointName=endpoint, ContentType="application/json", Body=json.dumps({
        "text": text, **voice, "format": "wav", "add_timestamps": True,
    }))
    body = json.loads(resp["Body"].read())
    with open(out, "wb") as f:
        f.write(base64.b64decode(body["audio"]))
    print(f"{body['duration_s']:.2f}s of audio in {time.perf_counter() - t0:.2f}s -> {out}")
    for w in body.get("words", [])[:10]:
        print(f"  {w['start']:6.2f}-{w['end']:6.2f}  {w['word']}")


def stream(endpoint: str, text: str, voice: dict, out: str) -> None:
    rt = boto3.client("sagemaker-runtime", region_name=REGION)
    t0 = time.perf_counter()
    resp = rt.invoke_endpoint_with_response_stream(
        EndpointName=endpoint, ContentType="application/json",
        Body=json.dumps({"text": text, **voice, "format": "mp3", "stream": True}),
    )
    first, n = None, 0
    with open(out, "wb") as f:
        for event in resp["Body"]:
            part = event.get("PayloadPart")
            if not part:
                continue
            first = first or time.perf_counter() - t0
            n += len(part["Bytes"])
            f.write(part["Bytes"])
    print(f"first audio {first * 1000:.0f} ms, {n:,} bytes in {time.perf_counter() - t0:.2f}s -> {out}")


async def bidi(endpoint: str, voice: dict, out: str) -> None:
    from aws_sdk_sagemaker_runtime_http2.client import SageMakerRuntimeHTTP2Client
    from aws_sdk_sagemaker_runtime_http2.config import Config, HTTPAuthSchemeResolver
    from aws_sdk_sagemaker_runtime_http2.models import (
        InvokeEndpointWithBidirectionalStreamInput,
        RequestPayloadPart,
        RequestStreamEventPayloadPart,
    )
    from smithy_aws_core.auth.sigv4 import SigV4AuthScheme
    from smithy_aws_core.identity import EnvironmentCredentialsResolver

    creds = boto3.Session().get_credentials().get_frozen_credentials()
    os.environ.update(AWS_ACCESS_KEY_ID=creds.access_key, AWS_SECRET_ACCESS_KEY=creds.secret_key)
    if creds.token:
        os.environ["AWS_SESSION_TOKEN"] = creds.token
    client = SageMakerRuntimeHTTP2Client(config=Config(
        endpoint_uri=f"https://runtime.sagemaker.{REGION}.amazonaws.com:8443",
        region=REGION,
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        auth_scheme_resolver=HTTPAuthSchemeResolver(),
        auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="sagemaker")},
    ))
    stream = await client.invoke_endpoint_with_bidirectional_stream(
        InvokeEndpointWithBidirectionalStreamInput(endpoint_name=endpoint))
    _, output = await stream.await_output()

    async def send(frame: dict) -> None:
        # UTF8 = WebSocket text frame; the container rejects binary input.
        part = RequestPayloadPart(bytes_=json.dumps(frame).encode(), data_type="UTF8")
        await stream.input_stream.send(RequestStreamEventPayloadPart(value=part))

    async def receive() -> dict | None:
        result = await asyncio.wait_for(output.receive(), 30)
        raw = getattr(getattr(result, "value", None), "bytes_", None) if result else None
        return json.loads(raw) if raw else None

    audio = bytearray()
    # An LLM's tokens arriving in pieces; sentences are synthesized as soon as they complete.
    turns = [["Thanks for calling Murf. ", "How can I ", "help you today?"],
             ["Sure, your order shipped ", "on Tuesday and arrives ", "on Thursday."]]
    await send({"type": "config", "data": {**voice, "format": "pcm_s16le", "sample_rate": 24000}})
    for i, pieces in enumerate(turns):
        t0 = time.perf_counter()
        for p in pieces:
            await send({"type": "text", "data": {"text": p}})
        await send({"type": "flush"})
        first = None
        while True:
            msg = await receive()
            if msg is None:
                raise RuntimeError("stream closed before the turn finished")
            if msg["type"] == "audio":
                first = first or time.perf_counter() - t0
                audio += base64.b64decode(msg["data"]["audio"])
            elif msg["type"] == "error":
                raise RuntimeError(msg["data"])
            elif msg["type"] == "event" and msg["data"]["event_type"] == "final":
                break
        print(f"turn {i}: first audio {first * 1000:.0f} ms, done {time.perf_counter() - t0:.2f}s")
    await stream.input_stream.close()
    try:
        while await receive() is not None:
            pass
    except (asyncio.TimeoutError, TimeoutError):
        pass
    with open(out, "wb") as f:
        f.write(audio)
    print(f"{len(audio) / 48000:.2f}s of 24 kHz s16le -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("endpoint")
    ap.add_argument("mode", choices=["realtime", "stream", "bidi"])
    ap.add_argument("--text", default="Hello from Murf Falcon on Amazon SageMaker. Streaming starts right away.")
    ap.add_argument("--voice", default="en-US-natalie")
    ap.add_argument("--locale", help="language to speak, from the voice's supported_locales")
    ap.add_argument("--style", help="speaking style for that locale")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    voice = {"voice_id": args.voice, **{k: v for k, v in (("locale", args.locale), ("style", args.style)) if v}}
    if args.mode == "realtime":
        realtime(args.endpoint, args.text, voice, args.out)
    elif args.mode == "stream":
        stream(args.endpoint, args.text, voice, args.out)
    else:
        asyncio.run(bidi(args.endpoint, voice, args.out))


if __name__ == "__main__":
    main()
