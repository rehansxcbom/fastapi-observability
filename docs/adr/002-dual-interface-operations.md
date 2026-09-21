# ADR 002: Dual-Interface Operations (Browser Control Panel & Bash Makefile)


**Date:** 19th September 2026 | **Status:** Accepted

  

### 1. Context and Problem Statement

Our current system enforces a diskless secrets management policy. To prevent credential leakage, we discourage `.env` files for database passwords, opting instead to inject credentials directly into the ephemeral Docker environment via interactive terminal prompts orchestrated by a `Makefile`. While this security posture is highly resilient, it introduces notable onboarding friction. Developers cannot simply run `docker-compose up`. They are required to use the `Makefile` and interactively supply passwords, requiring documentation reading. We need a solution that improves the developer experience (DX) for local testing without compromising our production security standards.
  
### 2. Architecture Decisions

**Decision:** Implement a browser-based Control Panel alongside the terminal onboarding flow.

**Rationale:** Having a secondary, browser-based setup method provides an accessible path for developers on operating systems lacking required development tools or on powershell avoiding workarounds like cygwin or msys2, requiring only Docker to be installed. Conversely, keeping the terminal-based flow ensures that users working on headless machines or on terminals can still onboard directly through the shell without any prior configurations.

**Decision:** Retain the bash-based `Makefile` exclusively for production operations.

**Rationale:** Production environments require automated, scriptable, and secure deployments. The `Makefile`ensures our diskless secrets management policy remains intact for live workloads, where credentials can be securely injected via CI/CD pipelines or secure terminal sessions.

### 3. Consequences

**Positive:** Onboarding becomes universally accessible across diverse development environments. The dual-method approach accommodates both developers missing traditional bash tooling (who can use the Control Panel) and developers in GUI-less/headless environments (who can use the terminal), completely removing the need for environment-specific workarounds.

**Positive:** Production environments retain their defense-in-depth security mechanisms, blocking credential leaks.

**Negative / Trade-offs:** The team must now maintain two parallel operational interfaces (the Control Panel app and the `Makefile`), ensuring both remain synchronized as the infrastructure evolves.
