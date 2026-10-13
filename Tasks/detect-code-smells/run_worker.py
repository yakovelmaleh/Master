#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Code_Smells_Detection.runtime.windows import main

if __name__ == "__main__":
    main()
