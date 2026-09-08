# OVAEL

### **Open-world AI for Network Threat Detection, Analysis & Response**

> **A network security system should not be forced to understand only what it has already seen.**

Ovael is a research-driven network security platform built around a simple observation:

**A network can produce behavior that does not fit anything a detection model has learned before.**

Traditional supervised intrusion detection works well when an attack belongs to a known category. But when the behavior changes, a new attack appears, or traffic falls outside the training distribution, classification alone becomes unreliable.

Ovael explores a different approach.

Instead of making one model responsible for the entire decision, Ovael separates the problem into two perspectives:

**Recognition** — *What does this traffic look like?*

**Novelty** — *Does this traffic look familiar at all?*

These perspectives are then brought together by an orchestration layer to produce a more informed security assessment.

---

## Why Ovael?

Imagine a model trained on:

```text
Normal
DoS
DDoS
Port Scan
Brute Force
Botnet
...
```

Now a new traffic pattern appears.

A conventional classifier still has to choose something from the categories it knows.

That creates a fundamental problem:

```text
                    New Traffic
                         |
                         ↓
                  "Which class?"
                         |
              +----------+----------+
              |                     |
              ↓                     ↓
        Known behavior       Unknown behavior
              |                     |
              ↓                     ↓
        Classification          Novelty
```

Ovael does not assume that every observation belongs to a known category.

It allows the system to recognize known behavior while independently questioning whether an observation is actually familiar.

That distinction is at the heart of the project.

---

# The Ovael Approach

Ovael is built around **two detection agents**.

They are not two copies of the same model doing the same job.

Each agent looks at network behavior from a different perspective.

```text
                         Network Traffic
                               |
                               ↓
                       Feature Extraction
                               |
                 +-------------+-------------+
                 |                           |
                 ↓                           ↓
          Detection Agent            Novelty Agent
                 |                           |
        "What is this?"              "Is this familiar?"
                 |                           |
                 +-------------+-------------+
                               |
                               ↓
                         Orchestrator
                               |
                               ↓
                         Risk Analysis
                               |
                               ↓
                       Security Decision
```

This allows Ovael to preserve information that would normally be lost when everything is reduced to a single classification.

---

# Detection Agent

The first agent focuses on **known network behavior**.

It uses a multiclass detection approach to identify traffic patterns represented in the training data.

Conceptually:

```text
Network Flow
     ↓
Feature Extraction
     ↓
Detection Agent
     ↓
Normal / Known Attack Class
```

Its primary question is:

> **"If I recognize this behavior, what is it?"**

This gives Ovael precise information when the traffic resembles a known pattern.

---

# Novelty Agent

The second agent has a different responsibility.

It does not try to force an unfamiliar observation into an existing attack category.

Instead, it evaluates how unusual the observation is relative to the behavior considered familiar.

```text
Network Flow
     ↓
Feature Extraction
     ↓
Novelty Agent
     ↓
Familiar / Novel
```

Its question is:

> **"Does this behavior fit within what I already understand?"**

This becomes particularly important when the system encounters an attack or traffic pattern that was not represented during training.

Research comparing supervised and anomaly-oriented approaches has shown the same underlying challenge: models can perform very strongly on familiar attacks while their ability to detect previously unseen attacks can drop significantly.

Ovael therefore treats **novelty as a first-class detection signal**, rather than an error condition.

---

# When Recognition and Novelty Disagree

This is where Ovael becomes particularly interesting.

Consider:

```text
Detection Agent
→ Normal

Novelty Agent
→ Highly Unusual
```

These results appear contradictory.

But they actually tell us something valuable.

The traffic may not match a known attack class, while still being significantly different from normal behavior.

Ovael does not immediately throw either result away.

Instead:

```text
             Detection Result
                    +
              Novelty Result
                    |
                    ↓
              Orchestrator
                    |
                    ↓
              Risk Analysis
```

The disagreement itself becomes part of the evidence.

This allows the system to represent situations such as:

```text
Known + Familiar
Known + Unusual
Normal + Familiar
Normal + Unusual
Unknown + Highly Unusual
```

Rather than reducing every observation to simply:

```text
Attack / Not Attack
```

---

# The Orchestrator

The Orchestrator is the layer responsible for bringing the outputs of the two agents together.

Its purpose is not simply to select whichever model has the highest confidence.

Instead, it creates a common decision context from the available signals.

```text
                    Traffic
                       |
              +--------+--------+
              |                 |
              ↓                 ↓
        Detection Agent   Novelty Agent
              |                 |
              |                 |
              +--------+--------+
                       |
                       ↓
                  Orchestrator
                       |
                       ↓
                  Risk Analysis
```

The Orchestrator allows the architecture to remain modular.

The detection agent can improve independently.

The novelty agent can be replaced or experimented with independently.

The decision layer can then evaluate how their outputs interact.

---

# Risk Analysis

A detection label by itself is often not enough.

Security decisions require context.

Ovael therefore introduces a risk-analysis stage after the two detection perspectives have been combined.

The system can consider signals such as:

```text
Attack Classification
        +
Classification Confidence
        +
Novelty Score
        +
Behavioral Evidence
        |
        ↓
    Risk Analysis
        |
        +---- Risk Score
        |
        +---- Severity
        |
        +---- Security Status
```

The objective is to distinguish between an ordinary observation, a known threat, an unfamiliar behavior, and an event that deserves immediate attention.

---

# Explainability

Detection without an explanation can make an automated security system difficult to trust.

Ovael therefore treats **explanation as part of the analysis pipeline**, rather than simply displaying a model prediction.

For a detected event, the system should be able to answer questions such as:

```text
Why was this traffic considered suspicious?

Which features influenced the decision?

Was the behavior recognized as a known attack?

Was it unusual even when no known attack was identified?

How confident was the system?

What evidence supports the assessment?
```

Feature-level explanation techniques can be used to expose which network characteristics influenced a model's decision.

This direction is inspired by research that combines ML classification with feature attribution and LLM-based incident reporting to make network-security predictions more interpretable and useful to analysts.

---

# From Detection to an Incident Explanation

Ovael is not intended to stop at:

```text
Attack Detected
```

The eventual goal is to transform raw model output into information that a security analyst can understand.

Conceptually:

```text
Network Event
      ↓
Detection
      ↓
Novelty Analysis
      ↓
Risk Assessment
      ↓
Evidence / Explanation
      ↓
Security Incident
```

The explanation layer can use the detection results and relevant contextual evidence to describe what happened and why the system considers it important.

This separates **prediction** from **interpretation**.

---

# Unknown Does Not Automatically Mean Malicious

One important principle of Ovael is:

> **Unknown ≠ malicious.**

An unusual network event may be:

* a new attack,
* a legitimate but previously unseen behavior,
* an application change,
* unusual user activity,
* or simply noise.

Therefore, novelty detection should not automatically convert every unknown observation into an attack.

Instead:

```text
                  Unusual Behavior
                         |
                         ↓
                    Investigation
                         |
                +--------+--------+
                |                 |
                ↓                 ↓
             Benign            Threat
```

This distinction is important for controlling false positives and for making the system useful outside controlled datasets.

---

# Learning From New Behavior

If an unknown behavior is investigated and confirmed to represent a meaningful new pattern, it can become useful future knowledge.

The intended feedback loop is:

```text
Unknown Behavior
       ↓
Novelty Detection
       ↓
Analysis
       ↓
Validation
       ↓
Curated Data
       ↓
Model Update
       ↓
Improved Detection
```

The validation step is important.

Ovael should not automatically learn from every anomaly it encounters.

Otherwise, incorrect detections could become part of the model's future understanding.

---

# A Controlled Network Environment

Ovael is designed to be evaluated in a controlled network environment rather than relying only on static datasets.

Traffic can be generated, captured, analyzed, and modified under repeatable experimental conditions.

```text
              Network Environment
                      |
          +-----------+-----------+
          |                       |
          ↓                       ↓
    Normal Traffic          Attack Traffic
          |                       |
          +-----------+-----------+
                      |
                      ↓
                Traffic Capture
                      |
                      ↓
               Feature Extraction
                      |
                      ↓
                   Ovael
```

This environment makes it possible to reproduce experiments and study how the system behaves under different traffic conditions.

---

# Testing What the Model Has Never Seen

A major focus of Ovael is **evaluation outside the comfortable training distribution**.

Instead of testing only:

```text
Training Data
      ↓
Similar Test Data
      ↓
High Accuracy
```

we also want to investigate:

```text
Training Knowledge
      ↓
Modified / Unseen Traffic
      ↓
Detection
      ↓
Novelty Response
      ↓
Risk Assessment
```

This lets us ask a more meaningful question:

> **What happens when the network behaves differently from what the system was trained to expect?**

---

# Adversarial Evaluation

Attack traffic can be modified without completely changing its underlying behavior.

That creates another important question:

> **How much can an attack change before the detection system stops recognizing it?**

Ovael can therefore be evaluated using controlled traffic modifications.

```text
Known Attack
     ↓
Traffic Modification
     ↓
Modified Attack
     ↓
+----------------------+
| Detection Agent      |
| Novelty Agent        |
| Risk Analysis        |
+----------------------+
     ↓
Compare Results
```

The goal is to understand not only whether the system detects an attack, but also **how its confidence and novelty assessment change as the behavior changes**.

---

# Multi-Agent Architecture

Ovael uses agents because the problem itself contains different responsibilities.

The architecture does not require a large collection of agents for every small task.

Instead, the system starts with two meaningful detection roles:

```text
             OVAEL
               |
       +-------+-------+
       |               |
       ↓               ↓
 Detection Agent   Novelty Agent
       |               |
       +-------+-------+
               |
               ↓
          Orchestrator
               |
               ↓
          Risk Analysis
               |
               ↓
         Final Assessment
```

This keeps the architecture understandable while allowing each agent to specialize.

Research into multi-agent intrusion detection also highlights the value of architectures that can adapt to changing attack patterns and accommodate new attack types.

---

# Scaling the System

The detection architecture is designed so that processing does not have to remain tied to a single running process.

As traffic and workload increase, different components can be replicated independently.

```text
                       Incoming Requests
                              |
                              ↓
                        Load Balancer
                              |
               +--------------+--------------+
               |              |              |
               ↓              ↓              ↓
            Backend-1      Backend-2      Backend-3
               |              |              |
               +--------------+--------------+
                              |
                              ↓
                            Queue
                              |
                    +---------+---------+
                    |                   |
                    ↓                   ↓
             Detection Workers   Novelty Workers
                    |                   |
                    +---------+---------+
                              |
                              ↓
                         Orchestrator
```

This allows the architecture to grow with demand without requiring every component to scale at the same rate.

The system can therefore be studied from two perspectives:

**How well does it detect?**

and

**How well does it continue to operate as workload increases?**

---

# What Ovael Is Trying to Explore

At its core, Ovael explores the boundary between **what a machine-learning security system knows and what it does not know**.

The system brings together:

```text
Known Attack Detection
          +
Novelty Detection
          +
Multi-Agent Reasoning
          +
Risk Assessment
          +
Explainability
          +
Adversarial Evaluation
          +
Controlled Learning
          +
Scalable Processing
```

But these are not treated as disconnected features.

They form one continuous process:

```text
Observe
   ↓
Understand
   ↓
Question
   ↓
Compare
   ↓
Assess
   ↓
Explain
   ↓
Learn
```

That is the idea behind **Ovael**.

---

## The Question We Keep Coming Back To

> ### **Can a network security system recognize the threats it knows, identify behavior it does not understand, and turn that uncertainty into useful security intelligence?**

Ovael is our attempt to investigate that question.

Not by assuming that one model can solve everything.

Not by treating every anomaly as an attack.

And not by assuming that tomorrow's network will behave like yesterday's dataset.

**The system should be able to recognize what it knows — and notice when something falls outside that knowledge.**
