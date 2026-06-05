# Something's wrong at Acme

You've just been pulled into the **Acme** engineering Slack. A teammate fires off a message and then disappears into meetings:

> "hey — something's clearly going sideways in prod right now and nobody's gotten to the bottom of it. can you dig in and figure out what's actually behind it? we'll need a clear writeup for the postmortem. you've got Slack access."

That's all you get. You don't know which service, which channel, or what the actual problem is.

You have Slack tools available (the `slack-cli` command and the `slack-mcp` MCP server, pointed at this workspace). Use them to look around, follow the conversation, and work out what's really causing the problem — don't guess, check. When you understand the root cause, post a clear writeup in the channel where the team is dealing with this, so it's captured for the postmortem.
