Q*BERT

This plugin plays Gottlieb's
1982 Q*bert arcade game on the
ColecoVision. It needs the
game's ROMs from MAME, which
you supply.

SETUP

1. Copy QBERT.CVP into the
   /PLUGINS folder on the
   card.
2. Make a folder named /QBERT
   and put the ROMs from
   MAME's qbert set in it. You
   can copy the 11 files
   loose, or copy qbert.zip as
   it is. You can also put the
   zip in the card's top
   folder as /QBERT.ZIP.
3. For Q*bert's voice, add
   sc01a.bin from MAME's
   votrsc01a set to the same
   folder, loose or as
   votrsc01a.zip, or put the
   zip in the top folder as
   /VOTRSC01A.ZIP. Without it
   the game plays with no
   speech.
4. Start Q*bert from the
   Plugins page in the menu.

The files can have any names,
because the plugin knows each
ROM by its size and contents.
If a ROM is missing, the
screen names it.

CONTROLS

Q*bert hops on the diagonals.
Hold the stick between two
directions, such as up and
right for up-right.

On the ColecoVision
controller:

- The joystick hops.
- Keypad * or # adds a coin.
- Keypad 1 starts a one-player
  game, and so does either
  fire button.
- Keypad 2 starts a two-player
  game.
- Press RESET on the console
  to go back to the menu, or
  hold both fire buttons and *
  for 2 seconds (Select and
  Start on a USB pad).

On a USB pad, through a
powered hub:

- The D-pad or the left stick
  hops.
- Minus adds a coin, and plus
  starts a one-player game.

A straight up, down, left or
right does nothing by itself.
If you roll from one diagonal
to the next through a straight
direction, the first diagonal
holds until you reach the next
one.

SAVES

High scores and the game's
settings are saved in
/QBERT/QBERT.NV when you press
RESET. Press RESET before you
turn the console off, or new
high scores are lost. The
/QBERT folder has to exist for
the save, even if your ROMs
are in /QBERT.ZIP.

QBERT.NV holds the same bytes
as MAME's nvram/qbert/nvram
file, so you can copy it
between the two.

PICTURE AND SOUND

The arcade screen stands on
its side and is 240 by 256
pixels. The ColecoVision shows
256 by 192, so the plugin
scales the picture to three
quarters of its size, 180 by
192, in the middle of the
screen. Colors are the nearest
of the ColecoVision's 15, with
the cubes' faces always kept
apart.

The sound board's DAC and
speech chip play through the
ColecoVision's sound chip as
5,962 samples a second.

CREDITS

The arcade emulation is a port
of MAME 0.288's code, under
the BSD-3-Clause license. Its
authors are:

- Fabrice Frances, Nicola
  Salmoria and Aaron Giles,
  for the Gottlieb driver.
- Aaron Giles, for the
  Gottlieb sound board, MAME's
  scheduler and the watchdog.
- Carl, for the 8088 CPU.
- Olivier Galibert, for the
  6502 CPU and the Votrax
  SC-01-A speech chip.
- Curt Coder, for the 6532
  RIOT chip.
- smf, for the DAC.
- Dirk Best and Vas Crabb, for
  the input merger.
- Couriersud, for the resistor
  network colors.

You can find MAME at
https://www.mamedev.org. The
zip reader follows Mark
Adler's puff, from zlib. USB
support comes from TinyUSB by
Ha Thach, under the MIT
license.

The plugin itself is by Parrot
Cart, and it's free. Its
source is linked next to its
download.

Q*bert is a trademark of its
owners. This plugin contains
none of the game.
