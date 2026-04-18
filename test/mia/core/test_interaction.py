import argparse
import asyncio

import nats


DEFAULT_NATS_URL = "nats://127.0.0.1:4222"
DEFAULT_SUBJECT = "maia.interaction.toggle"
DEFAULT_PAYLOAD = "toggle"


def _load_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Interactive helper that publishes toggle messages to the Maia pipeline.",
	)
	parser.add_argument(
		"--nats-url",
		default=DEFAULT_NATS_URL,
		help=f"NATS server URL (default: {DEFAULT_NATS_URL})",
	)
	parser.add_argument(
		"--subject",
		default=DEFAULT_SUBJECT,
		help=f"NATS subject to publish (default: {DEFAULT_SUBJECT})",
	)
	parser.add_argument(
		"--payload",
		default=DEFAULT_PAYLOAD,
		help=f"Message payload (default: {DEFAULT_PAYLOAD})",
	)
	return parser.parse_args()


async def _run(nats_url: str, subject: str, payload: str) -> None:
	nc = await nats.connect(nats_url)
	print(f"Connected to {nats_url}")
	print(f"Publishing to subject: {subject}")
	print("Press ENTER to send a toggle message. Ctrl+C to exit.")

	try:
		while True:
			await asyncio.to_thread(input)
			await nc.publish(subject, payload.encode("utf-8"))
			print(f"Published: {payload}")
	finally:
		await nc.drain()


def main() -> None:
	args = _load_args()
	try:
		asyncio.run(_run(args.nats_url, args.subject, args.payload))
	except KeyboardInterrupt:
		print("Exiting interactive publisher.")


if __name__ == "__main__":
	main()
