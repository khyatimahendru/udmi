# MANTIS Skill Extensibility Specification

This document defines the Skill Extensibility Subsystem for Mantis, detailing how operators and developers can expand Mantis's domain knowledge, protocols, troubleshooting playbooks, and hardware vendor rules simply by adding markdown skill files.

---

## 1. Design Philosophy: Modular Knowledge via Simple Markdown

Mantis is designed to be easily extensible without writing complex Python plugins or recompiling code. 

Adding domain expertise (such as BACnet MSTP integration, Modbus register mappings, OEM hardware controller quirks, or site-specific VLAN topologies) is as simple as creating a standard markdown file with YAML frontmatter: `SKILL.md`.

```
Knowledge & Skill Resolution Flow
├── Discovery: Mantis scans mantis/skills/ and sites/<site>/skills/ at startup.
├── Indexing:  Mantis loads skill names and descriptions into its prompt memory catalog.
└── Activation: When a user query or test run touches a domain, Mantis dynamically 
               loads the full SKILL.md instructions into its active context just-in-time.
```

---

## 2. Directory Structure & Locations

Skills can be defined at two levels:

1. **Global Built-in Skills (`mantis/skills/`)**:
   General domain knowledge, protocol standards, and architectural diagnostic guides that apply across all UDMI sites and devices.
2. **Site-Specific Skills (`sites/<site_name>/skills/`)**:
   Operational runbooks, network gateway topologies, and hardware vendor quirks specific to a particular building or deployment.

```
udmi/
├── mantis/skills/
│   ├── log-analysis/
│   │   └── SKILL.md          # Global log file catalogs & distributed tracing strategies
│   ├── component-guide/
│   │   └── SKILL.md          # UDMI component architecture and data flow rules
│   ├── bacnet-protocols/
│   │   └── SKILL.md          # BACnet MSTP/IP point mapping & discovery heuristics
│   └── modbus-gateways/
│       └── SKILL.md          # Modbus RTU/TCP register encoding & timeout guidelines
│
└── sites/
    └── my_site/
        └── skills/
            └── chiller-plant/
                └── SKILL.md  # Site-specific chiller sequence & gateway routing rules
```

---

## 3. Skill File Format (`SKILL.md`)

Each skill directory MUST contain a `SKILL.md` file formatted with standard YAML frontmatter:

```markdown
---
name: bacnet-protocols
description: Factual reference for BACnet MSTP and IP discovery, point mapping, and standard failure signatures in UDMI.
---

# BACnet Protocol & Discovery Guide

## 1. Overview & Pointset Mapping
In UDMI, BACnet object identifiers map to point names via the discovery envelope...

## 2. Common Failure Modes & Diagnostics
* **Discovery Enumeration Timeout**: If scan_periodic_now_enumerate fails, verify MS/TP token passing...
* **Engineering Unit Mismatches**: Ensure BACnet analog values map to UDMI standard physical units...

## 3. Investigation Strategy
When triaging BACnet device failures, inspect `device_system.log` for MSTP frame drop counts.
```

### 3.1. Frontmatter Requirements
* **`name`** *(Required)*: Unique alphanumeric identifier using kebab-case (e.g., `bacnet-protocols`, `log-analysis`).
* **`description`** *(Required)*: A concise 1-2 sentence description explaining what domain knowledge the skill provides and when Mantis should apply it.

---

## 4. Built-in Skill Catalog

Mantis includes standard built-in skills out of the box:

| Skill Name | Location | Focus Area |
| :--- | :--- | :--- |
| **`log-analysis`** | `mantis/skills/log-analysis/SKILL.md` | Distributed tracing by Transaction ID (`RC:...`), timestamp correlation, and handling missing telemetry streams. |
| **`component-guide`** | `mantis/skills/component-guide/SKILL.md` | Component boundaries (Pubber vs UDMIS vs Butler vs Sequencer), message pathways, and Java code entry points. |
| **`investigation-strategy`** | `mantis/skills/investigation-strategy/SKILL.md` | Systematic hypothesis pruning, boundary data probing, and differential timeline alignment heuristics. |

---

## 5. How to Add a New Skill (30-Second Guide)

To teach Mantis a new protocol, hardware quirk, or operational runbook:

1. Create a directory: `mkdir -p mantis/skills/<skill-name>`
2. Create `SKILL.md`:
   ```bash
   cat << 'EOF' > mantis/skills/<skill-name>/SKILL.md
   ---
   name: my-new-skill
   description: Explains how to triage and configure XYZ hardware in UDMI.
   ---

   # XYZ Hardware Triage Guide
   [Add instructions, failure signatures, and guidelines here]
   EOF
   ```
3. That's it! Mantis automatically discovers the skill on its next invocation.
