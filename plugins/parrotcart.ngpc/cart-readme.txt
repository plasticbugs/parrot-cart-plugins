NEO GEO POCKET COLOR

Plays Neo Geo Pocket Color and
Neo Geo Pocket games (.ngc and
.ngp files) on the
ColecoVision. The emulator is
NeoPop.

CONTROLS

- Stick: the Pocket's stick
- Left fire button: A
- Right fire button: B
- Keypad * or #: Option
- USB pad: d-pad or left
  stick, bottom button A,
  right button B, Start or the
  top and left buttons Option
- RESET, or both fire buttons
  and * held for 2 seconds
  (Select and Start on a USB
  pad): back to the menu. The
  game's save is written
  first.

WHAT IT NEEDS

- Your games on the card, in
  /NGPC or any folder. Press A
  on one in the menu to play
  it.
- A game's saves go in a .ngf
  file next to the game, with
  the game's name, in NeoPop's
  format. It's written a
  second after the game saves,
  and on the way back to the
  menu.
- For game pads, a powered USB
  hub between them and the
  cart, because the cart can't
  power them.
- No BIOS file. NeoPop stands
  in for the Pocket's BIOS,
  with English as the
  language.

WHAT TO EXPECT

- The Pocket's 160x152 screen
  sits in the middle of the
  TV. Each colour becomes the
  nearest ColecoVision colour,
  and each run of 8 pixels can
  show only two colours.
- The music and sound effects
  play on the ColecoVision's
  sound chip. Sampled sounds
  (some voices and drums)
  don't play.
- The cart has no clock, so
  the Pocket's clock starts at
  1 January 2026 each time.
- When a game is too busy for
  the cart, it skips pictures
  (up to two in a row) to keep
  the game at full speed. A
  few games that never rest,
  such as Big Bang Pro
  Wrestling, still run slower.
- Back in the menu, the note
  shows how it went, for
  example NGPC 100% 24P 0L
  19MS: the game's speed,
  pictures a second, TV frames
  the cart was late for, and
  the slowest frame in
  milliseconds. S at the end
  means a save was written,
  and SAVE! that one failed.

CREDITS

- NeoPop 0.71 by neopop_uk,
  GPL-2.0-or-later, as ported
  to the Raspberry Pi Pico by
  xrip:
  https://github.com/xrip/pico
  -neogeo-pocket
- The picture encoder from the
  Parrot Cart NES plugin,
  LGPL-2.1:
  https://github.com/plasticbu
  gs/parrot-plugin-nes
- The colour matching uses the
  Oklab colour space by Bjorn
  Ottosson:
  https://bottosson.github.io/
  posts/oklab/
- Parrot Cart plugin template
  and SDK, by the Parrot Cart
  contributors, MIT:
  https://github.com/plasticbu
  gs/parrot-plugin-template
- TinyUSB, by Ha Thach and
  contributors, MIT:
  https://github.com/hathach/t
  inyusb
- Raspberry Pi Pico SDK, BSD
  3-Clause:
  https://github.com/raspberry
  pi/pico-sdk

The Z80 that plays the sound
was written for this plugin
and checked against MAME's
(BSD 3-Clause) instruction by
instruction. It is MIT
licensed, so other plugins can
use it.

Source:
https://github.com/plasticbugs
/parrot-plugin-ngpc

LICENSE

GPL-2.0-or-later. See LICENSE.
The Z80 (src/ngpz80.c,
src/ngpz80.h) is MIT.
THIRD-PARTY.md lists the parts
that came from other projects,
and vendor/neopop/VENDORED.md
what was changed in NeoPop.

BUILDING

To build build/NGPC.CVP:

cmake -B build -G Ninja \
  -DPICO_SDK_PATH=$HOME/pico-s
ninja -C build

- test/ngpc.sh GAME plays it
  headless in the simulator,
  against the kit's models of
  the console, card and pads.
- test/z80check/run.sh runs
  the Z80 alongside MAME's and
  reports where they differ.
- sim/run.sh src --src
  '../vendor/neopop/*.c' --src
  '../vendor/neopop/TLCS-900h/
  *.c' --include vendor/neopop
  --include
  vendor/neopop/TLCS-900h
  --open GAME plays it in a
  window, with sound and
  controls.
- docs/getting-started.md:
  installing the tools, and
  using the card
- docs/release-checklist.md:
  what to check before you tag
  a release
