# xteink-ft8 bridge <-> device protocol (v1)

Transport: **TCP**, length-prefixed JSON messages. The X4 Pro is the client and
connects to the bridge's advertised address (the Pi's AP IP, e.g. `192.168.4.1`)
on **port 4510**.

## Framing

```
[4-byte big-endian uint32: payload length N][N bytes of UTF-8 JSON]
```

A single socket may carry many frames back to back. Both ends must read exactly
`N` bytes after the length prefix. Max payload 16384 bytes.

## Device -> Bridge (client commands)

Each command is a JSON object with a `cmd` field.

| cmd           | payload fields                                        | action |
|---------------|-------------------------------------------------------|--------|
| `hello`       | `{"cmd":"hello","version":1}`                          | announce device; bridge replies hello + snapshot |
| `get_status`  | `{}`                                                 | return current WSJT-X status |
| `get_decodes` | `{}`                                                 | return full decode list + seq |
| `reply`       | `{"decode_id":<int>}`                                 | answer a CQ decode (WSJT-X `Reply`) |
| `send_cq`     | `{"text":"CQ <CALL> <GRID>"}`                         | send free text with transmit (WSJT-X `FreeText`, send=1) |
| `send_freetext`| `{"text":"...","send":<bool>}`                      | set free text / Tx5, optionally send |
| `halt_tx`     | `{"auto_only":<bool>}`                                | stop TX (WSJT-X `HaltTx`) |
| `clear`       | `{"window":<int>}`                                    | clear WSJT-X window (0=band,1=rx,2=both) |
| `qsy`         | `{"band":"20m"}`  _or_ `{"freq_hz":<uint64>}`         | change band/frequency via rigctld (optional) |
| `decodes_ack` | `{"seq":<int>}`                                       | acknowledge decodes up to seq (bridge may GC) |
| `ping`        | `{}`                                                 | liveness check -> `pong` |

## Bridge -> Device (push / responses)

| type          | payload fields  | meaning |
|---------------|-----------------|---------|
| `hello`       | `{"ok":true,"version":1,"my_call":"..","my_grid":"..","mode":"FT8","band":"20m"}` | handshake reply |
| `status`      | `{...}`         | WSJT-X status snapshot (see below) |
| `decode`      | `{...}`         | a new CQ decode (see below) |
| `decodes`     | `{"seq":N,"decodes":[...]}` | full list snapshot (on `get_decodes` / after `hello`) |
| `clear_decodes`| `{}`          | all decodes cleared (WSJT-X Clear) |
| `qso_logged`  | `{...}`         | a QSO was logged |
| `no_such_decode` | `{"decode_id":N}` | requested decode no longer available |
| `not_supported` | `{"cmd":".."}` | command not supported by this build |
| `pong`        | `{}`            | reply to `ping` |
| `error`       | `{"message":".."}` | a recoverable error |

## Shared object shapes

### status object

```json
{
  "type": "status",
  "dial_freq": 14074000,
  "mode": "FT8",
  "dx_call": "K1ABC",
  "report": "-12",
  "tx_mode": "CQ",
  "tx_enabled": true,
  "transmitting": false,
  "decoding": true,
  "de_call": "W9XYZ",
  "de_grid": "EM48",
  "dx_grid": "FN20",
  "tx_message": "CQ W9XYZ EM48",
  "sub_mode": "NA",
  "special_operation_mode": 0,
  "tr_period": 15
}
```

> `tx_message` is the current outgoing message — this is what the device shows
> to visualize QSO progress.

### decode object

```json
{
  "type": "decode",
  "id": 42,
  "is_cq": true,
  "time": 43800,
  "snr": -8,
  "delta_time": 0.4,
  "delta_freq": 800,
  "mode": "FT8",
  "raw": "CQ K1ABC FN20",
  "call": "K1ABC",
  "grid": "FN20",
  "low_confidence": false,
  "off_air": false
}
```

* `id` is a stable per-bridge-session integer (monotonic). The device echoes it
  back in `reply`.
* `is_cq` is true when the bridge classified the message as a CQ/QRZ call.
* `call` and `grid` are parsed from `raw` when possible, else empty strings.

## Band change (`qsy`)

The bridge sends `qsy` to Hamlib `rigctld` (default `localhost:4532`) using its
text protocol: `F <freq_hz>;` (or `set_freq`). If `rigctld` is not reachable the
bridge replies `not_supported` and logs. WSJT-X picks up the new frequency via
its own rig polling. If the user prefers to set band manually, this command is
simply unused.

## Failure semantics

* Unknown command -> `error` (`{"message":"unknown command"}`).
* `reply` with a stale `decode_id` -> `no_such_decode` (the bridge prunes old
  decodes; the device should refresh its list).
* Socket errors are non-fatal; the device reconnects with backoff.