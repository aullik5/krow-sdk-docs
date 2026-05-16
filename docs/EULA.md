# Krow Agent SDK Runtime — End User License Agreement (EULA)

> Version: 1.1 (model legal review applied)
> Effective Date: 2026-05-13 (v1.0 draft) / 2026-05-15 (v1.1 model-review applied)
> Issuer: Krow Team (`support@krow.cn`)
> Status: **DRAFT — model legal review applied; pending external counsel sign-off + business decisions on §11 / §9 floor / §C consent mechanism**
>
> **Note** (v1.1, 2026-05-15): Sections marked `[PENDING ATTORNEY]` or
> `[PENDING BUSINESS]` are placeholders awaiting external counsel sign-off
> and business decisions respectively. Until v1.x reaches `EFFECTIVE`
> status, this document is published as a **good-faith disclosure** of
> intended terms. See [`eula-mock-legal-review-feedback.md`](./eula-mock-legal-review-feedback.md)
> for the full review log and rationale behind v1.0 → v1.1 changes.

---

## 1. Definitions

- **"Software"** means `krow-agent-sdk-runtime`, including all binary
  artifacts (`.so` / `.pyd`), Python source files (`.py`), static
  resources (`.yaml`, `.md`, etc.), and accompanying documentation
  distributed via GitHub Packages.
- **"Public SDK"** means `krow-agent-sdk` distributed via PyPI under
  the **Proprietary** license declared in `packages/krow-agent-sdk/pyproject.toml`
  (see `[project].license = { text = "Proprietary" }` and PyPI classifier
  `License :: Other/Proprietary License`). The Public SDK is gratis to
  install and use solely for the purpose of authoring plugins that integrate
  with the Software; it is **not** open-source under any OSI-approved
  license. **This EULA applies to the Software (runtime wheel) only;
  Public SDK usage is governed by `LICENSE` in the krow-agent-sdk
  distribution, which is consistent with this EULA's restrictions
  on redistribution and reverse engineering.**
- **"Krow Cloud"** means the SaaS platform operated by Krow Team at
  `https://api.krow.cn` and related domains.
- **"Licensee"** means the legal entity (individual or company) that
  has obtained a valid Krow API key and accepts the terms herein.
- **"Authorized User"** means a natural person within Licensee's
  organization permitted by Licensee to use the Software.
- **"Effective Date"** means, with respect to each version of this EULA,
  the date stated in the document header.
- **"PII" / "Personal Information"** means any information that, alone or
  combined with other accessible information, can identify a natural
  person, as defined under the PRC Personal Information Protection Law
  ("PIPL") and equivalent regulations (GDPR Art. 4(1) where applicable).
- **"Open Source Components"** means third-party software bundled with
  or required by the Software, each governed by its own license; see
  Appendix A for the non-exhaustive list and full SBOM via
  `python -m krow_agent_sdk._sbom`.

## 2. Grant of License

Subject to Licensee's compliance with this EULA and payment of any
applicable fees, Krow Team grants Licensee a **non-exclusive,
non-transferable, non-sublicensable, time-limited** license to:

- (a) Install the Software on machines owned or controlled by Licensee.
- (b) Use the Software solely for Licensee's internal business purposes
  (including but not limited to: development, testing, production
  deployment, customer support, and end-user-facing services) or to
  power Licensee's own products that integrate the Public SDK protocols.
- (c) Make a reasonable number of backup copies for disaster recovery.

## 3. Restrictions

Licensee SHALL NOT, and SHALL NOT permit any third party to:

- (a) **Reverse-engineer**, decompile, disassemble, or otherwise attempt
  to derive the source code or algorithms from the Software's compiled
  binaries (`.so` / `.pyd`), **except to the limited extent that such
  activity is expressly permitted by applicable law and is strictly
  necessary to achieve interoperability with Licensee's own software
  (e.g., Article 16 of the PRC Regulations on the Protection of Computer
  Software, Article 6 of EU Directive 2009/24/EC, or Section 60 of the
  Hong Kong Copyright Ordinance), and only after Licensee has requested
  and been denied the necessary interface information from Krow Team in
  writing**.
- (b) **Redistribute** the Software, in whole or in part, including but
  not limited to: re-uploading to PyPI, GitHub, mirrors, or sharing
  with anyone outside Licensee's organization.
- (c) **Re-brand** the Software (e.g., rename, fork, or claim
  authorship) and represent it as Licensee's own work.
- (d) **Bypass** authentication, license checks, telemetry, or
  rate-limiting mechanisms in the Software or Krow Cloud.
- (e) Use the Software to build a service that **competes directly**
  with Krow Cloud (e.g., agent orchestration as a managed service).
  However, **embedding the Software in Licensee's own products marketed
  primarily for purposes other than agent orchestration** (e.g., a
  vertical SaaS in legal / medical / engineering / industrial domains
  where agent capability is a feature rather than the headline offering)
  is **not** deemed competition under this clause.
- (f) Remove, modify, or obscure any copyright, trademark, watermark,
  or other proprietary notices embedded in the Software.
- (g) **Share, lend, transfer, or otherwise make available** any Krow
  API key across users (whether within or outside Licensee's organization)
  or organizations. Each Authorized User must use a unique API key
  associated solely with that User. Sharing a single API key among
  multiple Users is a **material breach** under §10(a).
- (h) Use the Software to develop or operate any service in a manner that
  violates **applicable AI service regulations** in Licensee's
  jurisdiction (including but not limited to PRC Generative AI Services
  Management Measures and equivalent algorithmic accountability rules).
  Compliance with such regulations is Licensee's sole responsibility.

## 4. Krow API Key

- (a) Each Authorized User is required to use a unique Krow API key
  obtained from Krow Cloud Dashboard.
- (b1) **API keys are personal**. Sharing an API key across users
  (whether within or outside Licensee's organization), lending, selling,
  or otherwise making API keys accessible to anyone other than the
  Authorized User is **strictly prohibited** and constitutes a material
  breach (see §3(g)).
- (b2) **Safeguarding**. Licensee is **solely responsible** for
  safeguarding API keys, including but not limited to: never committing
  keys to public Git repositories, encrypting keys at rest in CI / CD
  systems, rotating keys periodically (recommended every 90 days), and
  immediately revoking compromised keys via Krow Cloud Dashboard.
- (c) Krow Team may **revoke** any API key at any time for breach of
  this EULA, abuse, or security incidents. Revocation for **material
  breach** (e.g., key sharing per §3(g), bypassing rate limits per
  §3(d), or redistribution per §3(b)) is **immediate**. Revocation
  for non-material breach requires **thirty (30) days' written notice**
  to Licensee with opportunity to cure.
- (d) API key revocation will cause the Software to cease functioning
  on next install/update; existing installations may continue to run
  in **degraded mode** until next license check.

## 5. Telemetry & Privacy

- (a) The Software MAY collect **anonymous, aggregate** usage telemetry
  (such as version installed, OS, Python version, error types) to
  improve product quality.
- (b) Telemetry **WILL NOT** include: file contents, prompts, user
  data, or any personally identifiable information.
- (c) **Telemetry from the Public SDK is opt-in only and disabled by
  default.** Licensee MAY enable it by setting environment variable
  `KROW_SDK_TELEMETRY=1`; absence or any other value of this variable
  means **no telemetry is collected** by the Public SDK. Implementation
  SSOT: `modules/agent/sdk/telemetry.py`. Licensee may revoke this
  opt-in at any time by unsetting the variable. Past opted-in telemetry
  MAY be retained for up to **one hundred eighty (180) days** for
  product analytics and security incident investigation, after which
  it will be aggregated and the raw records purged. See also §6 below
  for runtime watermark, which is independent of this opt-in flag.
- (d) Krow Team's privacy policy is available at
  `https://krow.cn/legal/privacy` (when published; until then, refer
  to `docs/sdk/watermark-telemetry-design.md`).
- (e) **Negative list**. Telemetry SHALL NOT collect, transmit, or store
  any of the following categories, regardless of opt-in status:
    - LLM prompt or response content (including system prompts);
    - File path, filename, or file contents from Licensee's filesystem;
    - User-supplied API keys, passwords, or other authentication tokens;
    - Personally identifiable information (PII) of Licensee's end users;
    - Network packet payloads beyond version-string handshakes.
  Krow Team commits to **fail-loud build-time enforcement** of this
  negative list (see `modules/agent/sdk/telemetry.py:_NEVER_COLLECT`
  constant; CI deterministic-no-LLM gate verifies the list each build).

## 6. Watermarking

- (a) Each Software wheel installed via `krow-sdk-install` may include
  a **per-licensee fingerprint** (an opaque identifier tied to
  Licensee's account). This fingerprint:
    - **By default** the watermark identifier remains **local only** and
      is **not transmitted** by the Software during normal operation;
    - Is transmitted to Krow Team **only** when (i) Licensee explicitly
      enables telemetry per §5(c), or (ii) Krow Team conducts a forensic
      investigation following a confirmed leak under §6(b);
    - Is used solely to identify the source of any leaked binary.
- (b) Discovery of leaked Software bearing Licensee's fingerprint
  outside Licensee's organization shall constitute prima facie evidence
  of breach.

## 7. Intellectual Property

- (a) The Software is and remains the exclusive property of Krow Team
  and/or its licensors. All rights not expressly granted are reserved.
- (b) **Public SDK** (`krow-agent-sdk`) is distributed under a Proprietary
  license (see `packages/krow-agent-sdk/pyproject.toml`); however, Krow
  Team grants Licensee a perpetual, royalty-free right to reference the
  Public SDK's protocols, error types, and facade APIs to develop
  Licensee's own plugin code. **Licensee's plugin source code that only
  imports from `krow_agent_sdk.*` (and does not embed Software binaries
  nor copy non-trivial portions of the Public SDK source) remains the
  exclusive property of Licensee** and is not a derivative work of the
  Software within the meaning of this EULA. **Mere invocation** of Krow
  ACT YAML files or built-in prompt templates from Licensee's plugin
  code does not transform the plugin into a derivative work of the
  Software, **provided that** Licensee does not extract, copy, or
  redistribute the prompt content separately from the Software.

## 8. Disclaimer of Warranties

THE SOFTWARE IS PROVIDED "AS IS" AND "AS AVAILABLE", WITHOUT WARRANTY
OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
NON-INFRINGEMENT.

**Specifically with respect to LLM-generated output**: Krow Team makes no
warranty regarding the accuracy, completeness, fitness, or legality of
any output generated by Large Language Models invoked through the
Software. Licensee is solely responsible for evaluating and verifying
all such output before use, and for any consequences arising from
reliance on such output.

## 9. Limitation of Liability

IN NO EVENT SHALL KROW TEAM BE LIABLE FOR ANY INDIRECT, SPECIAL,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING BUT NOT LIMITED TO
LOSS OF PROFITS, DATA, OR USE, ARISING OUT OF OR IN CONNECTION WITH
THE SOFTWARE.

In no event shall Krow Team's aggregate liability exceed the **greater
of**: (i) the fees paid by Licensee to Krow Team in the **twelve (12)
months** preceding the event giving rise to the claim, or (ii)
**[PENDING BUSINESS DECISION: liability floor amount, e.g., USD 1,000
or RMB 5,000 — to be set by Krow Team in consultation with external
counsel]**.

## 10. Termination

- (a) This EULA terminates automatically upon Licensee's **material
  breach** (including but not limited to §3(b) redistribution, §3(g)
  key sharing, or §3(d) bypassing license checks).
- (b) Licensee may terminate by uninstalling the Software and ceasing
  use.
- (c) Upon termination, Licensee SHALL within **thirty (30) days**:
    - (i) Cease all use of the Software;
    - (ii) Uninstall the Software from all machines on which it was
      installed pursuant to §2(a);
    - (iii) Destroy or securely overwrite any cached binaries
      (`.so` / `.pyd` files in `~/.krow/runtime/` or equivalent paths,
      including Docker image layers if applicable);
    - (iv) Confirm destruction in writing within fifteen (15) days of
      Krow Team's written request, signed by an officer of Licensee.

## 11. Governing Law and Dispute Resolution

This EULA shall be governed by **[PENDING BUSINESS DECISION:
governing law jurisdiction — see `eula-mock-legal-review-feedback.md`
§P0-3 for options A (PRC + CIETAC Beijing + Chinese), B (Hong Kong +
HKIAC + English), or C (Singapore + SIAC + English)]**, without regard
to conflict-of-law principles.

Any dispute arising out of or in connection with this EULA shall be
**resolved by arbitration** at the institution selected per the
governing-law decision above, conducted in the language stated therein.
The award of the arbitration shall be **final and binding** on both
parties.

Notwithstanding the above, Krow Team reserves the right to seek
**injunctive or equitable relief** in any court of competent
jurisdiction to enforce its intellectual property rights under §3 and
§7.

## 12. Contact

- Sales: `sales@krow.cn`
- Legal: `legal@krow.cn`
- Support: `support@krow.cn`
- EULA inquiries / data subject requests: `legal@krow.cn`

## 13. Severability

If any provision of this EULA is held to be invalid, illegal, or
unenforceable by a court of competent jurisdiction or arbitral tribunal,
such provision shall be deemed modified to the minimum extent necessary
to make it valid, legal, and enforceable; if such modification is not
possible, the provision shall be severed, and the remaining provisions
shall continue in full force and effect.

## 14. Force Majeure

Neither party shall be liable for any failure or delay in performance
under this EULA (other than payment obligations) due to causes beyond
its reasonable control, including but not limited to: acts of God,
natural disasters, war, terrorism, civil unrest, governmental orders or
regulations, pandemic, internet or telecommunications failures, or
shortages of materials.

The affected party shall: (i) promptly notify the other party in
writing; (ii) use reasonable efforts to mitigate the impact; (iii)
resume performance as soon as practicable. If a force majeure event
continues for more than **ninety (90) days**, either party may
terminate this EULA on written notice without further liability.

## 15. Assignment

- (a) **Licensee MAY NOT** assign, sublicense, or transfer this EULA
  or any rights or obligations hereunder, in whole or in part, by
  operation of law or otherwise, without Krow Team's prior written
  consent. Any unauthorized assignment shall be null and void.
- (b) **Krow Team MAY** assign this EULA to: (i) any affiliate; (ii) any
  successor in connection with a merger, acquisition, reorganization,
  or sale of all or substantially all of Krow Team's assets or business
  pertaining to the Software, **provided that** the assignee assumes
  Krow Team's obligations hereunder. Krow Team shall provide Licensee
  with reasonable notice of any such assignment.

## 16. Audit Rights

Krow Team may, **upon thirty (30) days' prior written notice and during
Licensee's normal business hours**, audit Licensee's compliance with
this EULA, including but not limited to: number of installations,
number of Authorized Users, deployment configurations, and license-key
usage patterns. Audits shall:

- (a) Be conducted by Krow Team or an independent third-party auditor
  bound by confidentiality obligations no less protective than those
  herein;
- (b) Not occur more than once per twelve (12) months unless Krow Team
  has a **good-faith reason** to believe a material breach has occurred;
- (c) Be performed in a manner that minimizes disruption to Licensee's
  business operations;
- (d) Not access PII of Licensee's end users, or any data outside the
  scope necessary to verify compliance.

If an audit reveals material breach, Licensee shall reimburse Krow
Team's reasonable audit costs in addition to any other remedies.

## 17. Survival

The following provisions shall **survive any termination or expiration**
of this EULA: §1 (Definitions), §3 (Restrictions, in their entirety),
§5 (Telemetry & Privacy, with respect to data already collected), §6(b)
(watermark forensics), §7 (Intellectual Property), §8 (Disclaimer), §9
(Limitation of Liability), §10(c) (Termination obligations), §11
(Governing Law), §12 (Contact), §13 (Severability), and §17 itself.

## 18. Entire Agreement

This EULA, together with any **Order Form**, **Master Services
Agreement**, or **Data Processing Agreement** (collectively, "Ancillary
Documents") executed by Krow Team and Licensee, constitutes the
**entire agreement** between the parties with respect to the Software
and supersedes all prior or contemporaneous communications,
representations, or agreements, whether oral or written.

In the event of conflict between this EULA and any Ancillary Document,
the Ancillary Document shall prevail to the extent of the conflict,
**provided that** the Ancillary Document is signed by an authorized
representative of both parties.

No modification of this EULA shall be effective unless in writing and
signed by both parties; no waiver of any provision shall be effective
unless in writing.

---

## Appendix A: Known Open-Source Dependencies

The Software bundles or depends on the following open-source software,
each governed by its respective license:

| Component | License | Used For |
|---|---|---|
| Cython | Apache-2.0 | Build-time compilation toolchain |
| python-pptx | MIT | PPTX file manipulation |
| python-docx | MIT | DOCX file manipulation |
| openpyxl | MIT | XLSX file manipulation |
| PyMuPDF | AGPL-3.0 | PDF rendering (used in optional `[office]` extras) |
| Pillow | HPND | Image manipulation |
| pycairo | LGPL-2.1 | SVG rasterization (used in optional `[office]` extras via `svglib`) |

A complete SBOM (CycloneDX format) is bundled with each release and
available via `python -m krow_agent_sdk._sbom`.

**LGPL-2.1 components disclosure**: Components licensed under LGPL-2.1
(notably `pycairo`) are dynamically linked at runtime; Licensee retains
the right to relink against modified versions of such LGPL components,
and Krow Team will provide upon written request the necessary
information (build flags, header files, ABI version) to enable such
relinking. Contact `legal@krow.cn` for relinking requests.

**AGPL-3.0 components disclosure**: PyMuPDF (`pymupdf`) is licensed
under AGPL-3.0 and is included **only in optional `[office]` extras**.
If Licensee operates the Software as a network service in a manner that
triggers AGPL-3.0 §13 (network use as distribution), Licensee shall
either: (i) make the corresponding source code available to network
users per AGPL-3.0 terms, or (ii) install the Software without the
`[office]` extras to exclude PyMuPDF.

---

## Appendix B: Acceptance

By installing or using the Software, Licensee:

1. Acknowledges having read and understood this EULA
2. Agrees to be bound by all terms and conditions herein
3. Represents authority to bind their organization

If Licensee does not agree, Licensee SHALL NOT install or use the
Software, and SHALL request a refund (if applicable) within 14 days
of purchase.

---

## Appendix C: Acceptance Mechanism (v1.1, model legal review)

To establish **provable, time-stamped consent** under PRC PIPL Article 14
("explicit consent") and equivalent regulations (GDPR Art. 7), Krow Team
implements the following **three-layer acceptance mechanism**:

### C.1 Primary layer — Krow Cloud account creation

When Licensee creates a Krow Cloud account or generates a new API key,
Licensee is presented with the EULA in full and **must explicitly
check** an "I have read and agree to the EULA" checkbox before the API
key is issued. The Krow Cloud backend records:

- `consent_timestamp` (UTC, ISO 8601)
- `user_id` (Krow Cloud account identifier)
- `client_ip` (originating IP address)
- `eula_version_hash` (SHA-256 of the EULA document content)
- `user_agent` (browser or CLI client identifier)

These records are retained for **the lifetime of the account plus
seven (7) years** for legal evidence purposes.

### C.2 Secondary layer — `krow-sdk-install` CLI

When Licensee first runs `krow-sdk-install` on a machine, the CLI
checks for `~/.krow/eula-accepted.json` (or platform equivalent). If
absent, the CLI:

- (i) Displays the EULA URL and version;
- (ii) Prompts: `Do you accept the EULA in full? [y/N]`;
- (iii) On `y`, writes a local consent record (timestamp + EULA version
  hash) and reports the consent event to Krow Cloud (aggregate, no PII);
- (iv) On `N`, aborts installation with a clear message.

### C.3 Tertiary layer — install-time disclosure

`docs/sdk/runtime-install.md` and PyPI package long description
prominently link to this EULA at `https://krow.cn/eula` (when published)
with the notice: "By installing krow-agent-sdk-runtime, you accept the
EULA at the linked URL."

### Legal effect of three-layer mechanism

The combined evidentiary force of all three layers — Cloud-side server
records (C.1) + local CLI consent record (C.2) + install-time
disclosure (C.3) — is intended to satisfy:

- **PRC PIPL Article 14**: explicit, voluntary, specific, informed consent
- **GDPR Article 7**: demonstrable consent (where applicable)
- **PRC Contract Law**: meeting of the minds for click-wrap agreement
- **Common-law jurisdictions**: assent by conduct + record-keeping

**Final selection** between the three layers (whether all three are
mandatory or only C.1 + C.3 baseline) is **[PENDING BUSINESS DECISION
+ external counsel sign-off]**. Implementation roadmap: see
[`eula-legal-review-checklist.md`](./eula-legal-review-checklist.md) §6.

---

> **NOTE TO LICENSEE**: This is a **DRAFT v1.1** template. Material
> differences (if any) from prior versions or future revisions will be
> communicated to existing Licensees with at least **thirty (30) days'**
> notice; continued use after the effective date of revisions
> constitutes acceptance.
