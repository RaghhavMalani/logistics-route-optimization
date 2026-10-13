"""Import an existing AIS JSONL recording into the JNPA arrival evidence archive."""
import argparse
from pathlib import Path

from src.portwatch_os.fabric.ais.messages import AisMessageError, normalise
from src.portwatch_os.fabric.ais.recorder import ObservationRecorder
from src.portwatch_os.intelligence.arrivals import archive_track
from src.portwatch_os.ledger.store import get_ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    args = parser.parse_args()
    if not args.recording.is_file():
        parser.error("Recording must be an existing JSONL file")
    ledger = get_ledger()
    accepted = rejected = 0
    for index, (received, envelope) in enumerate(ObservationRecorder.read(args.recording), 1):
        try:
            observation = normalise(envelope, now=received, raw_ref=f"archive:{args.recording.name}:{index}")
            accepted += archive_track(ledger, observation)
        except AisMessageError:
            rejected += 1
    print(f"Eligible JNPA reports processed: {accepted}; invalid envelopes: {rejected}. Existing IDs deduplicate.")
    print("Source/receipt times are preserved. Recording time is now; imports cannot create earlier replay knowledge.")


if __name__ == "__main__":
    main()
