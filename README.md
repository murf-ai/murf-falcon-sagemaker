# Murf Falcon text-to-speech: usage

Murf Falcon turns text into natural speech in 22 locales and 155 voices. It runs
entirely inside your AWS account with network isolation: text and audio never
leave the endpoint.

- Real-time endpoint: `InvokeEndpoint` returns the complete audio.
- Streaming endpoint: `InvokeEndpointWithResponseStream` returns audio as it is
  generated; first audio typically arrives in 50-60 ms.
- Bidirectional streaming: `InvokeEndpointWithBidirectionalStream` accepts text in
  pieces (for example from an LLM) and returns audio per sentence.
- Batch transform: one JSON request per S3 object, one audio file per output object.

## Recommended instances

| Instance | GPU | Concurrent streams per instance |
|---|---|---|
| ml.g6e.xlarge (recommended) | NVIDIA L40S 48 GB | 32 |
| ml.g6.xlarge | NVIDIA L4 24 GB | 16 |
| ml.g5.xlarge | NVIDIA A10G 24 GB | 16 |
| ml.g6.12xlarge | 4x NVIDIA L4 24 GB | 64 |

The 2xlarge and 4xlarge sizes of these families are also supported, plus
ml.g6e.12xlarge; batch transform runs on ml.g6e.xlarge, ml.g6.xlarge and ml.g5.xlarge. Requests beyond the
instance's concurrent streams queue for up to 2 seconds and then receive HTTP 429;
scale out with more instances or SageMaker auto scaling.

## Input

`Content-Type: application/json`

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes | Text to speak. Up to 3,000 characters per real-time request, 20,000 when streaming. |
| `voice_id` | string | yes | Voice to use, e.g. `en-US-natalie`. Send `{"action": "list_voices"}` for the catalog. |
| `format` | string | no | `wav` (default), `mp3`, `ogg_opus`, `flac`, `pcm_s16le`, `pcm_f32le`, `mulaw`, `alaw`. Streaming defaults to `mp3`; `flac` cannot be streamed. |
| `sample_rate` | integer | no | 8000, 16000, 22050, 24000 (default), 44100 or 48000. |
| `locale` | string | no | Override the voice's locale, e.g. `hi_IN`. |
| `speed` | number | no | 0.5-2.0, default 1.0. |
| `pitch` | number | no | 0.5-2.0, default 1.0. |
| `volume_db` | number | no | -10 to 10. |
| `stream` | boolean | no | `true` with `InvokeEndpointWithResponseStream`. |
| `stream_format` | string | no | `raw` (audio bytes, default) or `ndjson` (audio chunks and word timestamps as JSON lines). |
| `add_timestamps` | boolean | no | Return word start and end times. Streaming needs `stream_format: ndjson`. |
| `response_format` | string | no | `json` (default) or `binary` (audio bytes only) for real-time and batch requests. |
| `normalize_text` | boolean | no | Expand numbers, dates and abbreviations before speaking. Default `true`. |

Example:

```json
{"text": "Hello from Murf Falcon on Amazon SageMaker.", "voice_id": "en-US-natalie", "format": "wav"}
```

## Output

Real-time requests return JSON:

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

`words` is present only with `add_timestamps`. With `"response_format": "binary"`
the body is the audio file itself.

Streaming requests return the audio bytes in the requested format as they are
generated, or JSON lines when `stream_format` is `ndjson`.

Batch transform writes one output object per input object. Use
`"response_format": "binary"` to get playable audio files.

Errors return a JSON body `{"error": {"code": ..., "message": ..., "status": ...}}`
with the matching HTTP status.

## Pricing

Real-time and streaming endpoints bill software usage per 1,000 input
characters. Batch transform jobs bill per instance hour, because AWS Marketplace
offers only hourly pricing for batch. Both are in addition to the SageMaker
instance cost.

## Samples

- Notebook: `Murf-Falcon-TTS-on-SageMaker.ipynb`
- Requests: `samples/`
