# Mr. Do!

This plugin lets Parrot Cart play Universal's 1982 Mr. Do! arcade game on the ColecoVision. The cart emulates the arcade board, ported from MAME. You supply the game's ROMs from your own copy of MAME's `mrdo` set.

## What goes on the card

1. Copy `MRDO.CVP` into the `/PLUGINS` folder.
2. Make a folder named `/MRDO` and put MAME's `mrdo.zip` in it as it is, or the files from it loose. You can also put the zip in the card's top folder as `/MRDO.ZIP`.
3. Start Mr. Do! from the menu.

The plugin knows each ROM by its size and contents, so the file names don't matter. If a ROM is missing, the screen names it. If a file has a ROM's name but different contents, from another version of the game or a bad copy, the screen names that too.

## Controls

On the ColecoVision controller:

- The joystick moves Mr. Do.
- Either fire button throws the power ball.
- Keypad * or # adds a coin.
- Keypad 1 starts a one-player game, and keypad 2 a two-player game.
- RESET on the console goes back to the menu, and so does holding both fire buttons and \* for 2 seconds (Select and Start on a USB pad).

On a USB pad, through a powered hub:

- The D-pad or the left stick moves Mr. Do.
- Any face button throws the ball.
- Minus adds a coin, and plus starts a one-player game.

The arcade stick has four ways. On a diagonal, Mr. Do goes the way you pressed last, as in MAME.

## Picture and sound

The arcade screen stands on its side, 192 by 240 pixels. The playfield is shrunk to seven eighths of its size and sits in the middle of the TV. The scores and lives go on the left, and the scene number and the EXTRA letters on the right.

Colors are the nearest of the ColecoVision's 15. A few are picked by hand so the cherries, apples and dirt stay apart. Round 1's dirt turns maroon in the arcade while a letter monster is out. Here it turns dark yellow, because dark red would hide the red fruit.

The arcade board has two sound chips with six tones between them. The ColecoVision has one chip with three, so the three loudest play at any moment. About one moment in ten, that leaves a tone out.

The dip switches are MAME's defaults: 3 lives, easy, one coin a credit. High scores last until you go back to the menu.

## Credits

The arcade emulation is a port of MAME 0.288's code, under the BSD-3-Clause license. Its authors are:

- Nicola Salmoria, for the Mr. Do! driver and the SN76496 sound chip.
- Juergen Buchmueller and Andrei I. Holub, for the Z80 CPU.
- Aaron Giles, for MAME's scheduler, screen and tilemaps.

You can find MAME at https://www.mamedev.org. The zip reader follows Mark Adler's puff, from zlib. USB support comes from TinyUSB by Ha Thach, under the MIT license. The plugin is built with the Raspberry Pi Pico SDK (BSD-3-Clause) and the Parrot Cart SDK (MIT).

The plugin is by Parrot Cart, and it's free. Its source is here: https://github.com/plasticbugs/parrot-plugin-mrdo

Mr. Do! is a trademark of Universal. Parrot Cart isn't connected with them. This plugin doesn't include any game ROMs.

## Build it yourself

You need the Raspberry Pi Pico SDK 2.1.1, an Arm GNU toolchain, CMake,
Ninja, Python 3, sjasmplus and picotool. Releases are built with the Arm
GNU Toolchain 9-2019-q4 (GCC 9.2.1) and picotool 2.3.1. With those you get
the same file as the release, byte for byte.

```sh
cmake -B build -G Ninja -DPICO_SDK_PATH=$HOME/pico-sdk
ninja -C build
```

This makes `build/MRDO.CVP`. On Ubuntu, `tools/ci/setup.sh` installs the
same tools GitHub uses to build each release.

`CART-README.md` is the text the cart shows on the plugin's page.
`test/mrdo/README.md` has the tests against MAME and what they measured.
The rest of this repository is the Parrot Cart starter kit, and `docs/` is
its manual.

## License

The plugin is under the BSD 3-Clause license (`LICENSE`). `THIRD-PARTY.md`
lists the parts that came from elsewhere, and their licenses.
