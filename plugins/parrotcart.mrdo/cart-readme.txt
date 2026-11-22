MR. DO!

This plugin plays Universal's
1982 Mr. Do! arcade game on
the ColecoVision. It needs the
game's ROMs from MAME, which
you supply.

SETUP

1. Copy MRDO.CVP into the
   /PLUGINS folder on the
   card.
2. Make a folder named /MRDO
   and put MAME's mrdo.zip in
   it as it is, or the files
   from it loose. You can also
   put the zip in the card's
   top folder as /MRDO.ZIP.
3. Start Mr. Do! from the
   Plugins page in the menu.

The files can have any names,
because the plugin knows each
ROM by its size and contents.
If a ROM is missing, the
screen names it. If a file has
a ROM's name but different
contents, from another version
of the game or a bad copy, the
screen names that too.

CONTROLS

On the ColecoVision
controller:

- The joystick moves Mr. Do.
- Either fire button throws
  the power ball.
- Keypad * or # adds a coin.
- Keypad 1 starts a one-player
  game, and keypad 2 a
  two-player game.
- Press RESET on the console
  to go back to the menu.

On a USB pad, through a
powered hub:

- The D-pad or the left stick
  moves Mr. Do.
- Any face button throws the
  ball.
- Minus adds a coin, and Plus
  starts a one-player game.

The arcade stick has four
ways. A diagonal moves Mr. Do
the way you pressed last, as
in MAME.

PICTURE AND SOUND

The arcade screen stands on
its side and is 192 by 240
pixels. The ColecoVision's is
256 by 192, so the plugin
shrinks the playfield to seven
eighths of its size, 168 by
182, and puts it in the
middle. The scores, the high
score and the lives move to
the left of it. The scene
number and the EXTRA letters
move to the right, with the
letters stacked in a box.

Mr. Do, the monsters, the
apples and the ball are the
ColecoVision's sprites while
there is room on their lines.
The rest is drawn into the
picture, where two colors
share each row of 8 pixels.

Colors are the nearest of the
ColecoVision's 15, with a few
picked by hand so the
cherries, apples and dirt stay
apart.

The arcade board has two sound
chips with six tones between
them. The ColecoVision has one
chip with three. At each
moment the three loudest play,
at the arcade's pitches and
levels.

High scores last until you go
back to the menu, as on the
arcade machine when it's
switched off.

CREDITS

The arcade emulation is a port
of MAME 0.288's code, under
the BSD-3-Clause license. Its
authors are:

- Nicola Salmoria, for the Mr.
  Do! driver and the SN76496
  sound chip.
- Juergen Buchmueller and
  Andrei I. Holub, for the Z80
  CPU.
- Aaron Giles, for MAME's
  scheduler, screen and
  tilemaps.

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

Mr. Do! is a trademark of
Universal. This plugin
contains none of the game.
