# **Security Policy**

Known Systems AI, Inc. takes the security of this project seriously. This document explains how to report vulnerabilities and what you can expect from us in return.

## **Supported Versions**

| Version | Supported |
| :---- | :---- |
| Latest commit on `main` | ✅ |
| Earlier commits | ❌ |

The skills are installed from `main`, so a fix reaches users when they update the plugin or reinstall
the skills.

## **What Counts as a Vulnerability**

These skills are instructions that coding agents follow. Guidance that would lead an agent to write
insecure code or set up an insecure deployment is a security issue here: for example, code that
accepts an unverified or revoked identity, fails open where it should fail closed, logs or commits
private keys or tokens, or lets a prompt choose where signed requests go. Report it privately, not in
a public issue.

## **Reporting a Vulnerability**

**Please do not report security vulnerabilities through public GitHub issues, pull requests, or discussions.**

Report privately through one of the following:

- **GitHub Security Advisories**: if the **"Report a vulnerability"** button is available under
  this repository's **Security** tab, use it to open a private advisory.
- **Email**: `security@dnsid.ai`

## **Our Commitment**

When you report a vulnerability responsibly, we will:

- **Acknowledge** receipt within **3 business days**.  
- Provide an **initial assessment** (validity, severity, next steps) within **14 days**.

## **How Fixes Are Released**

Installed copies of the skills cannot be recalled, so the remedy for a confirmed vulnerability is a fix
on `main` plus an advisory:

1. The fix is merged to `main` and the plugin version in `.claude-plugin/plugin.json` is increased, so
   plugin installs see an update.
2. A GitHub Security Advisory is published on this repository at the same time, describing the
   affected guidance and the fixing commit. There is no separate mailing list.
3. Reporters are credited in the advisory unless they ask otherwise.

A report showing guidance that leads code to accept an invalid record, signature, or status **as
valid** is treated as the highest priority.

## **Non-Security Problems Found After Publication**

If a published release is found to contain a licensing defect, third-party material we may not
distribute, personal data, or anything else that should not have been published, we follow the same
path as a security fix: the material is removed on `main`, with a notice in the README and an
advisory where warranted. Because installed copies and git history cannot be truly recalled, we will
also remove the material from the repository history where that is possible. Archiving the repository is the last resort. The decision is made by the
company's legal team; the security owner executes it. Report such problems to `security@dnsid.ai`; they
are routed to legal.

## **Remediation Timelines and Support Period**

Beyond the acknowledgement and assessment commitments above, we do not currently commit to fixed
remediation deadlines or to a defined security-support period. Security fixes are provided on `main` on
a best-effort basis. This position will be revisited; any change will be
made in this file first.

## **End of Life**

If maintenance of a project ends, we will say so in its README and a final commit, point to any
successor, and archive the repository
read-only rather than delete it so that existing installs keep resolving. Forks remain free to continue
under the Apache-2.0 and CC BY 4.0 licenses.

## **Support**

These skills are provided under the Apache License 2.0 and CC BY 4.0 without warranty. Issues and
pull requests are triaged on a best-effort basis by the maintainers. No commercial
support is attached to these repositories.

## **Safe Harbor**

We will not pursue or support legal action against researchers who:

- Act in good faith and in accordance with this policy,  
- Avoid privacy violations, service disruption, and destruction/exfiltration of data beyond what is needed to demonstrate the issue, and  
- Give us a reasonable time to respond before disclosing.

*This policy applies to this open-source project only. It does not create any obligation with respect to Known Systems' commercial products or services.*
