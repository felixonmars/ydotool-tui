# ydotool-tui

Small dependency-free terminal UI for sending common keyboard and mouse events
through [`ydotool`](https://github.com/ReimuNotMoe/ydotool).

It can run locally or execute `ydotool` commands on a remote machine over SSH.

## Requirements

- Python 3 with the standard `curses` module
- `ydotool` installed on the target machine
- `ydotoold` running on the target machine
- permission to access the `ydotoold` socket

On Arch Linux, `ydotool` installs a user service:

```sh
systemctl --user start ydotool.service
```

Or for a manual session:

```sh
sudo ydotoold
```

## Usage

Run locally:

```sh
./ydotool-tui
```

Run against a remote machine:

```sh
./ydotool-tui --ssh user@host
```

Use a custom daemon socket on the target:

```sh
./ydotool-tui --socket /run/user/1000/.ydotool_socket
```

Preview commands without sending input:

```sh
./ydotool-tui --dry-run
```

List the built-in actions:

```sh
./ydotool-tui --list-actions
```

Run the tests:

```sh
python -m unittest discover -s tests -v
```

## Controls

- `Up` / `Down`: move selection
- `Enter`: send selected action
- `/`: filter actions
- `k`: send a key combo, such as `ctrl-alt-t`, `c-a-t`, or `alt-f2`
- `t`: free typing; printable keys send immediately
- `Ctrl+]`: leave free typing
- `m`: mouse mode; move with `WASD` or arrows
- `Space` / `Enter`: left click in mouse mode
- mouse mode `c` / `r` / `x` / `b` / `f` / `2`: left, right, middle, back, forward, or double click
- mouse mode `h` / `j` / `k` / `l`: wheel left, down, up, or right
- `q` / `Ctrl+]`: leave mouse mode
- menu `c`: prompt for a mouse button click
- `?`: help
- `q`: quit

The built-in action list keeps high-frequency keys, arrows, clicks,
`Ctrl+C`, `Ctrl+D`, `Ctrl+L`, `Ctrl+Alt+T`, `Alt+Tab`, and `Alt+F4`.
Use `k` for other key combos.
