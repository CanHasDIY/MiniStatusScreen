# Mini Status Screen - A Python Script

This script is designed to work in Windows 10/11 with Turing IPS (and compatible) USB screens. I'm working on a Debian script but it's not working right yet.

## Installation
Clone the repo and enter the directory:
```
gh repo clone CanHasDIY/MiniStatusScreen

cd MiniStatusScreen
```

Install the dependencies:
```
pip install -r requirements.txt
```

## How To Use The Script
For 5 inch screens, run 

```
python stats5.py
```

For 3.5 inch screens, run
```
python stats3.5.py
```

## Acknowledgements
Thanks to [mathoudebine](https://github.com/mathoudebine) for his [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python/) project upon which this project is
based. Also, thanks to [majormer](https://github.com/majormer) for the original script written for 5 inch screens, all I did was modify the code to work on a 3.5 inch screen. 
See [here](https://github.com/mathoudebine/turing-smart-screen-python/discussions/664) for the original discussion.
