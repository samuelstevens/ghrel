# ghrel

I wanted to install releases from GitHub for lots of different packages (ripgrep, fd, lazygit, jj, etc.) without depending on my package manager (brew) to update them.
I also wanted to install some tools that suggest `npm install -g` (codex, gemini, pi, opencode) without using `npm install -g`.

ghrel is a simple tool for writing your own packages, using pre-compiled binaries from GitHub, without depending on upstream dependencies or package managers.
Package files are written in Python.

**You write your own package files.**
