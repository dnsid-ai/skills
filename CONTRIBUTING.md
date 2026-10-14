# Contributing to the DNSid agent skills

The skills are instructions a coding agent follows, so a good change is
accurate, tells the agent what to do rather than what DNSid is in general, and
helps someone build with DNSid. If it does not help a user or an agent build
with DNSid, it does not belong here.

## Changing a skill

1. Each skill is `skills/<name>/SKILL.md`, with longer material in
   `skills/<name>/references/`. Keep `SKILL.md` short and move detail to a
   reference file that `SKILL.md` links to.
2. Check every command, API, and default against the CLI, the SDKs, or
   [docs.dnsid.ai](https://docs.dnsid.ai) before you write it. A claim that
   cannot be checked does not go in.
3. Examples use reserved names only, such as `alice.test`, `agent.example`, and
   `example.com`. Never check in a real domain, account ID, key, or token.
4. Keep the secure default in every example: verification fails closed, keys
   stay out of logs and git, and the code checks the destination before it
   signs a request.

## Pull requests

- Branch off `main`. Changes reach `main` only through a pull request, and
  commits must be signed.
- Increase the version in `.claude-plugin/plugin.json` when a change should
  reach existing plugin installs.

## Licensing of contributions

This project does not use a CLA or DCO (inbound = outbound). By contributing
you agree that your prose is licensed under CC BY 4.0 (`LICENSE-docs.txt`), and
your code, including code blocks in Markdown, under the Apache License 2.0
(`LICENSE`), matching the rest of the repository. Do not copy code or text from
sources under other licenses.

## Security

If a skill would lead an agent into insecure code or an insecure setup, report
it per `SECURITY.md` rather than in a public issue.
