# Capturing the real end-to-end demo

The repo already ships a local-listener map screenshot as proof the chain works.
These steps add the strongest possible evidence: a **real Signal chat** and a
**real iTAK marker** from one live run. Only you can take these — they need your
phone and your iTAK device.

> **Redact your phone number before committing.** Your Signal number (E.164)
> appears in the chat header and in the bot's logs. This is a public repo — draw
> a solid box over the number in every screenshot and replace it with
> `+380XXXXXXXXX` in any pasted log. (The CoT XML itself contains no phone
> number — only lat/lon/description — so `sample_cot.xml` is safe as-is.)

## Prerequisites (one terminal each)

1. Link + daemon (see the main README §2–3):
   ```bash
   signal-cli -a +YOURNUMBER daemon --http=127.0.0.1:8080 --receive-mode=on-connection
   ```
2. Bot pointed at your iTAK device (same Wi-Fi):
   ```bash
   COT_URL=udp://239.2.3.1:6969 python -m signal_atak        # try multicast first
   # or, if multicast is dropped:  COT_URL=tcp://<ipad_ip>:4242
   ```
3. iTAK open on the iPad/iPhone (for the TCP route, add the input under
   **Settings → Network → Inputs/Outputs**).

## The shots

### 1. `signal_chat.jpg` — the Signal side
- In Signal, open **Note-to-Self** and send: `48.567123 39.87897 tank`
- Wait for the bot's reply: `✅ sent tank @ 48.567123, 39.87897 → …`
- Screenshot the chat showing **both** the sent message and the reply.
- **Redact** your number/name in the header.

### 2. `itak_marker.jpg` — the ATAK side
- On the iTAK map, the marker should appear at ~48.57, 39.88 with callsign
  `tank-XXXX`.
- Tap it to open the detail card (shows the type `a-h-G-E-V-A-T` and the
  remarks); screenshot the map with the marker (and, if you like, a second shot
  of the detail card).

### 3. (optional) `terminal.jpg` — the wire
- The bot's terminal showing `emitted tank (48.567123, 39.87897) → …`, or run
  once with `COT_URL=log://stdout` to capture the raw CoT XML.
- Redact the number if it shows in a log line.

## Finishing

- Save as JPEG, ~1200 px wide, into `docs/demo/` with the names above.
- Send them over and they'll be wired into the README's **Live demo (real
  device)** section and committed. (Optimising size / final crop can be done at
  that point.)
