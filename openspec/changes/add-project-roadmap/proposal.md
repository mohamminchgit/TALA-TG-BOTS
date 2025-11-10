# Change: Structure Project Roadmap

## Why
`openspec/project.md` captures the full vision for the Telegram arbitrage bot, but there is no actionable OpenSpec roadmap to guide staged delivery. We need a proposal that extracts the document into sequenced capabilities so the build can start step by step.

## What Changes
- Add a new `project-roadmap` capability that translates the directives in `openspec/project.md` into staged, testable requirements.
- Define sequential phases covering infrastructure, trading strategies, risk management, and management tooling.
- Provide a granular task list so future work can be executed and tracked against the spec.

## Impact
- Affected specs: `project-roadmap`
- Affected code: future changes across `src/bot_agent`, `src/engine`, `src/common`, `src/config`
