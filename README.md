# Murf Falcon Text-to-Speech on Amazon SageMaker

Murf Falcon is a low-latency text-to-speech model for voice agents, IVR and
narration: 141 voices in 42 locales, first audio in about 50 ms when streaming.
It is sold on AWS Marketplace as a SageMaker model package and runs entirely
inside your AWS account with network isolation, so text and audio never leave
your endpoint.

This repository has everything you need to start:

| Path | What it is |
|---|---|
| [`Murf-Falcon-TTS-on-SageMaker.ipynb`](Murf-Falcon-TTS-on-SageMaker.ipynb) | Notebook: deploy, list voices, real-time, streaming, word timestamps, batch transform, clean up |
| [`examples/invoke.py`](examples/invoke.py) | Command-line client for real-time, response streaming and bidirectional streaming |
| [`samples/`](samples) | Example requests and a response for each mode |

**Contents:** [Getting started](#getting-started) ·
[Choosing a voice, language and style](#choosing-a-voice-language-and-style) ·
[Ways to call the endpoint](#ways-to-call-the-endpoint) · [Request reference](#request-reference) ·
[Instances and performance](#instances-and-performance) · [Troubleshooting](#troubleshooting) ·
[Security and privacy](#security-and-privacy) · [Pricing](#pricing) · [Versions](#versions) · [Support](#support)

## Getting started

About 15 minutes, most of it waiting for the endpoint to start.

### 1. Check prerequisites

- **Permissions.** To subscribe: `AWSMarketplaceManageSubscriptions` (or the
  `aws-marketplace:ViewSubscriptions`, `Subscribe` and `Unsubscribe` actions).
  To deploy: `AmazonSageMakerFullAccess` and `iam:PassRole` on a SageMaker
  execution role. SageMaker Studio and notebook instances already have such a role.
- **GPU quota.** In Service Quotas → Amazon SageMaker, check
  `ml.g6e.xlarge for endpoint usage` is at least 1. For batch transform also check
  `ml.g6e.xlarge for transform job usage`; it is 0 by default in many accounts.
  If ml.g6e is not available in your Region, use ml.g6.xlarge or ml.g5.xlarge.

### 2. Subscribe and copy the model package ARN

1. Open the [Murf Falcon listing](https://aws.amazon.com/marketplace/search/results?searchTerms=Murf+Falcon)
   and choose **Continue to subscribe**.
2. Review pricing, EULA and support terms, then choose **Accept offer**.
3. Choose **Continue to configuration**, pick your **Region** and copy the
   **Product ARN**. It is different in every Region.

Already subscribed? Go to AWS Marketplace → **Manage subscriptions**, open Murf
Falcon, choose **Configure** (or **Launch new instance**), select **AWS CLI** and
your Region, and copy the ARN.

### 3. Deploy an endpoint

Run the [notebook](Murf-Falcon-TTS-on-SageMaker.ipynb): paste the ARN into its
first cell, nothing else needs changing. Or with boto3:

```python
import boto3, time

region = "us-east-1"                                        # the Region you copied the ARN for
model_package_arn = "<model package ARN from step 2>"
role = "arn:aws:iam::<account-id>:role/<sagemaker-execution-role>"
name = f"murf-falcon-{time.strftime('%Y%m%d-%H%M%S')}"

sm = boto3.client("sagemaker", region_name=region)
sm.create_model(ModelName=name, ExecutionRoleArn=role,
                PrimaryContainer={"ModelPackageName": model_package_arn},
                EnableNetworkIsolation=True)
sm.create_endpoint_config(EndpointConfigName=name, ProductionVariants=[{
    "VariantName": "AllTraffic", "ModelName": name,
    "InstanceType": "ml.g6e.xlarge", "InitialInstanceCount": 1,
    "ContainerStartupHealthCheckTimeoutInSeconds": 900,
}])
sm.create_endpoint(EndpointName=name, EndpointConfigName=name)
sm.get_waiter("endpoint_in_service").wait(EndpointName=name, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
```

The endpoint is ready in about 8-10 minutes.

### 4. Generate speech

```python
import base64, json

runtime = boto3.client("sagemaker-runtime", region_name=region)
resp = runtime.invoke_endpoint(EndpointName=name, ContentType="application/json", Body=json.dumps({
    "text": "Hello from Murf Falcon on Amazon SageMaker.",
    "voice_id": "en-US-natalie",
    "format": "wav",
}))
body = json.loads(resp["Body"].read())
open("hello.wav", "wb").write(base64.b64decode(body["audio"]))
```

Or from a terminal:

```bash
python examples/invoke.py "$ENDPOINT" realtime --text "Hello there." --out hello.wav
```

### 5. Clean up

You pay for the instance while the endpoint runs, whether or not you send requests.
Delete it when you are done:

```python
sm.delete_endpoint(EndpointName=name)
sm.delete_endpoint_config(EndpointConfigName=name)
sm.delete_model(ModelName=name)
```

Your subscription stays active, so you can deploy again later. To end it, delete
your models first, then cancel it under AWS Marketplace → **Manage subscriptions**.

## Choosing a voice, language and style

Ask the endpoint for its catalog:

```python
voices = json.loads(runtime.invoke_endpoint(
    EndpointName=name, ContentType="application/json",
    Body=json.dumps({"action": "list_voices"}))["Body"].read())["voices"]
```

Each voice looks like this:

```json
{
  "id": "en-US-natalie", "name": "Natalie", "gender": "female", "locale": "en_US",
  "styles": ["Conversation"],
  "supported_locales": {"en_US": ["Conversation"]},
  "description": "Young Adult"
}
```

- `locale` is the language a voice speaks by default.
- `supported_locales` lists every language the voice can speak and the styles
  available in each. Many voices speak several languages natively, so one voice
  can serve a multilingual product.
- Send `locale` and `style` with a request to choose. Both are optional: the
  default is the voice's own locale and the first style listed for it.

```json
{"text": "ನಮಸ್ಕಾರ, ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?", "voice_id": "pa-IN-harman", "locale": "kn_IN"}
```

## Ways to call the endpoint

| Mode | API | Use it for |
|---|---|---|
| Real-time | `InvokeEndpoint` | Complete audio in one response (up to 3,000 characters) |
| Response streaming | `InvokeEndpointWithResponseStream` | Voice agents and long text: audio arrives as it is generated (up to 20,000 characters) |
| Bidirectional streaming | `InvokeEndpointWithBidirectionalStream` | Text arriving in pieces, for example LLM tokens; audio comes back per sentence |
| Batch transform | `CreateTransformJob` | Folders of requests in S3, one audio file per request |

**Response streaming.** Add `"stream": true`. The response is the audio file
itself in `mp3` (default), `wav`, `ogg_opus` or raw PCM, written as it is
generated. With `"stream_format": "ndjson"` you get JSON lines instead:
`{"type": "chunk", "data": "<base64>"}`, `{"type": "timestamps", ...}` and a final
`{"type": "done"}`.

```bash
python examples/invoke.py "$ENDPOINT" stream --text "Hello there." --out hello.mp3
```

**Bidirectional streaming.** One session carries many turns. Send JSON text
frames; the endpoint answers with JSON frames:

| You send | Endpoint sends |
|---|---|
| `{"type": "config", "data": {"voice_id": "en-US-natalie", "format": "pcm_s16le"}}` (any request field; send again to change settings) | `{"type": "event", "data": {"event_type": "ready", ...}}` |
| `{"type": "text", "data": {"text": "Thanks for calling. "}}` as often as you like | `{"type": "audio", "data": {"audio": "<base64>", ...}}` for each finished sentence |
| `{"type": "flush"}` to end a turn and speak any remaining text | `{"type": "event", "data": {"event_type": "final", "turn": 0}}` |
| `{"type": "cancel"}` to stop speaking (barge-in) | `{"type": "event", "data": {"event_type": "cancelled"}}` |
| `{"type": "close"}` | the session ends |

`examples/invoke.py ... bidi` is a complete client. It needs
`pip install aws-sdk-sagemaker-runtime-http2` (Python 3.12+), because boto3 does
not support this API yet.

**Batch transform.** Put one JSON request per S3 object, set `ContentType`
`application/json` and `SplitType` `None`, and use `"response_format": "binary"`
to get playable audio files. The notebook has a complete example.

## Request reference

`Content-Type: application/json`

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | Text to speak. Up to 3,000 characters per real-time request, 20,000 when streaming. |
| `voice_id` | string | yes | Voice to use, e.g. `en-US-natalie`. Send `{"action": "list_voices"}` for the catalog. |
| `locale` | string | no | Language to speak, e.g. `hi_IN`; one of the voice's `supported_locales`. Defaults to the voice's `locale`. |
| `style` | string | no | Speaking style, one of the voice's styles for that locale. Defaults to the first. |
| `format` | string | no | `wav` (default), `mp3`, `ogg_opus`, `flac`, `pcm_s16le`, `pcm_f32le`, `mulaw`, `alaw`. Streaming defaults to `mp3`; `flac` cannot be streamed. |
| `sample_rate` | integer | no | 8000, 16000, 22050, 24000 (default), 44100 or 48000. `mulaw` and `alaw` default to 8000. |
| `speed` | number | no | 0.5-2.0, default 1.0. |
| `pitch` | number | no | 0.5-2.0, default 1.0. |
| `volume_db` | number | no | -10 to 10. |
| `normalize_text` | boolean | no | Expand numbers, dates, currencies and abbreviations before speaking. Default `true`. |
| `add_timestamps` | boolean | no | Return word start and end times. Streaming needs `stream_format: ndjson`. |
| `stream` | boolean | no | `true` with `InvokeEndpointWithResponseStream`. |
| `stream_format` | string | no | `raw` (audio bytes, default) or `ndjson`. |
| `response_format` | string | no | `json` (default) or `binary` (audio bytes only) for real-time and batch requests. |

Real-time requests return JSON ([sample](samples/realtime_response.json)):

```json
{
  "request_id": "6f1c...",
  "audio": "<base64 audio>",
  "content_type": "audio/wav",
  "sample_rate": 24000,
  "duration_s": 2.84,
  "usage": {"characters": 43},
  "words": [{"word": "Hello", "start": 0.08, "end": 0.41}]
}
```

`words` is present only with `add_timestamps`.

Errors return `{"error": {"code": ..., "message": ..., "status": ...}}`:

| Status | `code` | Meaning |
|---|---|---|
| 400 | | Malformed request; the message names the field |
| 400 | `text_too_long` | Over the character limit for this mode |
| 404 | `voice_not_found` | Unknown `voice_id` |
| 422 | `unsupported_locale`, `unsupported_language` | The voice does not speak that language; the message lists the ones it does |
| 422 | `unsupported_style` | The style is not offered for that voice and locale; the message lists the styles |
| 429 | `capacity_exceeded` | All synthesis slots busy for 2 seconds; retry or scale out |
| 503 | `not_ready` | The model is still loading |

## Instances and performance

| Instance | GPU | Concurrent streams per instance |
|---|---|---|
| ml.g6e.xlarge (recommended) | NVIDIA L40S 48 GB | 32 |
| ml.g6.xlarge | NVIDIA L4 24 GB | 16 |
| ml.g5.xlarge | NVIDIA A10G 24 GB | 16 |
| ml.g6.12xlarge | 4x NVIDIA L4 24 GB | 64 |

The 2xlarge and 4xlarge sizes of these families and ml.g6e.12xlarge are also
supported. Batch transform runs on ml.g6e.xlarge, ml.g6.xlarge and ml.g5.xlarge.
Requests beyond the concurrent streams queue for up to 2 seconds and then receive
HTTP 429; scale out with more instances or
[SageMaker auto scaling](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling.html).

Measured on one ml.g6e.xlarge in November 2026, streaming 157-character requests
from a client in the same Region:

| Concurrent streams | Median time to first audio |
|---|---|
| 1 | 44 ms |
| 10 | 60 ms |
| 32 | 84 ms |

Intelligibility: 1.0-1.4% word error rate when Falcon's English output for ten
passages is transcribed by a speech recognizer, across three voices.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ResourceLimitExceeded` when creating the endpoint or transform job | Request a quota increase for that instance type (step 1), or use another supported type. |
| `InsufficientInstanceCapacity` | Try again later, another instance type, or another Region. |
| `Could not assume role` | The execution role must trust `sagemaker.amazonaws.com`. New roles take a few seconds to become usable. |
| Endpoint fails its health check | Keep `ContainerStartupHealthCheckTimeoutInSeconds` at 900; loading the model takes a few minutes. |
| HTTP 429 under load | Add instances or enable auto scaling; each instance serves the concurrent streams listed above. |
| 422 for a voice in another language | Check the voice's `supported_locales`; not every voice speaks every language. |

The endpoint writes one line per request to CloudWatch Logs
(`/aws/sagemaker/Endpoints/<endpoint-name>`) with character count, audio length
and latency. Text is never logged.

## Security and privacy

- Your text and audio stay in your account. The model runs with SageMaker network
  isolation, so the container has no network access and sends nothing to Murf or
  any third party.
- Everything the model needs is inside the model package; nothing is downloaded
  at start-up.
- Generated audio carries an inaudible [AudioSeal](https://github.com/facebookresearch/audioseal)
  watermark that identifies it as synthetic speech.

## Pricing

Real-time and streaming endpoints are billed per 1,000 input characters. Batch
transform jobs are billed per instance hour, because AWS Marketplace offers only
hourly pricing for batch. Both are in addition to the SageMaker instance cost.
See the listing for current prices.

## Versions

| Version | Notes |
|---|---|
| 1.0.1 | Initial release: 141 voices in 42 locales; voice styles and cross-language voices; real-time, response streaming, bidirectional streaming and batch transform. |

## Support

Email [support@murf.ai](mailto:support@murf.ai) with your endpoint's Region,
the model package version and the request ID from the response.
