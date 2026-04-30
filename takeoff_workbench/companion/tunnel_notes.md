# Cloudflare Tunnel Notes

Takeoff Workbench is local-first. The companion server binds to `127.0.0.1` by
default and is off unless explicitly launched.

`run_companion_tunnel.bat` is an operator-controlled convenience launcher. It:

1. Warns that the local companion will be exposed through Cloudflare Tunnel.
2. Starts the local companion launcher.
3. Runs `cloudflared tunnel --url http://127.0.0.1:8787`.

The project does not install `cloudflared`, create named tunnels, or auto-start
tunnels. Write actions still require `TAKEOFF_COMPANION_TOKEN`.

For company deployment, prefer a named tunnel with Cloudflare Access and an
identity policy. Do not rely only on the quick tunnel URL being hard to guess.
