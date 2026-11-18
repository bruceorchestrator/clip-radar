# Clip Radar

Self-hosted clipping machine for stream clipping campaigns: finds the moments viewers already
clipped on Twitch, cuts them into vertical clips with captions (webcam on top, game below),
checks each clip against the campaign's rules and posts it only when you click.
About a fraction of a cent per clip on a $20/month server.

**Using an AI agent (Claude Code, Codex, Cursor...)?** Give it this repo and say:

> Read docs/AGENT_GUIDE.md. Explain to me how this system works, then set it up with me step by
> step and ask me for the keys you need.

Everything is in [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md): how the chain works, setup from
zero, config, campaign rules, and how to add Kick or other platforms.

Built on [OpenShorts](https://github.com/mutonby/openshorts) (the clipping core, used unmodified).
