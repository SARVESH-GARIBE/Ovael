# OVAEL

### **Open-world AI for Network Threat Detection, Adaptation & Response**

> **A security system should not become helpless simply because an attack changes its appearance.**

Ovael is a research-oriented network security system built around a simple idea:

**Known attacks can be detected from what the system has already learned. Unknown attacks require the system to recognize that something does not fit its existing knowledge — and then learn from validated discoveries.**

Traditional intrusion detection systems are generally evaluated on their ability to classify attacks that are already represented in their training data. This works well when the future resembles the past.

But real networks do not work that way.

Attackers can modify traffic patterns. New attack techniques can appear. Previously unseen behavior can fall outside the distribution a model was trained on.

When that happens, a classifier may still try to assign the traffic to a class it knows.

**Ovael explores what happens when the system is allowed to say:**

> **"I don't recognize this behavior."**

And, more importantly:

> **"Let me investigate whether it represents something worth learning."**

---

# The Core Idea

Ovael is designed around two complementary detection paths.

```text
                         NETWORK TRAFFIC
                                |
                                ↓
                       Feature Extraction
                                |
                 ┌──────────────┴──────────────┐
                 |                             |
                 ↓                             ↓
          KNOWN ATTACK PATH              UNKNOWN PATH
                 |                             |
                 ↓                             ↓
          Detection Model               Novelty Detection
                 |                             |
                 |                             ↓
                 |                        Unfamiliar
                 |                         Behavior
                 |                             |
                 |                             ↓
                 |                       Investigation
                 |                             |
                 |                             ↓
                 |                        Validation
                 |                             |
                 |                       ┌─────┴─────┐
                 |                       ↓           ↓
                 |                    Benign      Attack
                 |                       |           |
                 |                       |           ↓
                 |                       |      Self-Learning
                 |                       |           |
                 |                       |           ↓
                 |                       |      Model Update
                 |                       |           |
                 └───────────────────────┴───────────┘
                                             |
                                             ↓
                                      Improved Detection
```

The important distinction is that **known attack detection and unknown attack discovery are not treated as the same problem.**

---

# Known Attacks

The first path handles behavior the system already knows.

A supervised detection model can learn from labeled network traffic and identify known categories.

```text
Network Flow
     ↓
Feature Extraction
     ↓
Detection Model
     ↓
Known Class
```

For example:

```text
Normal
DoS
DDoS
Port Scan
Brute Force
Botnet
...
```

The Detection Model answers:

> **"What known behavior does this traffic resemble?"**

This gives Ovael a strong foundation for detecting threats that are already represented in its learned knowledge.

---

# Unknown Attacks

The more difficult problem begins when traffic does not resemble the behavior the Detection Model has learned.

Instead of forcing that traffic into a known category, Ovael introduces a separate **Novelty Detection** path.

```text
Network Flow
     ↓
Feature Extraction
     ↓
Novelty Detection
     ↓
Familiar / Unfamiliar
```

The Novelty component asks:

> **"Does this behavior fit within what the system already understands?"**

This is fundamentally different from asking which known attack class a flow belongs to.

An observation can therefore be:

```text
Known + Familiar
Known + Unusual
Normal + Familiar
Normal + Unusual
Unknown + Highly Unusual
```

The distinction matters because:

> **Unknown does not automatically mean malicious.**

An unfamiliar observation could represent a legitimate change, unusual activity, noise, or a genuinely new attack.

That is why Ovael does not immediately learn from every anomaly.

---

# The Self-Learning Loop

This is the central research direction of Ovael.

When the system encounters behavior that appears unfamiliar, the observation enters an investigation and validation process.

```text
Unknown Behavior
       ↓
Novelty Detection
       ↓
Investigation
       ↓
Validation
       ↓
      ┌───────────────┐
      │               │
      ↓               ↓
   Benign          Confirmed Attack
      │               │
      ↓               ↓
   Discard       Curated Knowledge
                      │
                      ↓
                 Model Update
                      │
                      ↓
              Improved Detection
```

The critical principle is:

> **Ovael should not blindly learn from anomalies.**

A novelty signal is only the beginning.

The system must first determine whether the behavior represents something meaningful.

Only validated behavior should be considered for incorporation into future knowledge.

This creates an evolving detection cycle:

```text
Observe
   ↓
Detect
   ↓
Discover Novelty
   ↓
Investigate
   ↓
Validate
   ↓
Learn
   ↓
Detect Better
```

The objective is to investigate whether a security system can become progressively more capable of recognizing attack behavior that was not part of its original knowledge.

---

# Adversarial Behavior

A major part of Ovael's research is understanding what happens when a known attack is deliberately modified.

An attacker does not necessarily need to invent a completely new attack.

They may alter characteristics of an existing attack so that its network representation looks different from what the detection model has seen.

Ovael therefore studies a process such as:

```text
Known Attack
     ↓
Adversarial Modification
     ↓
Modified Attack
     ↓
Detection Model
     ↓
Does it still recognize it?
```

If the modified behavior is no longer confidently recognized:

```text
Modified Attack
      ↓
Novelty Detection
      ↓
Unfamiliar Behavior
      ↓
Investigation
      ↓
Validation
      ↓
Confirmed Threat
      ↓
Self-Learning
      ↓
Future Detection
```

This gives us an important research question:

> **Can a system use novelty detection and validated learning to adapt when known attacks are modified to appear unfamiliar?**

---

# Why Adversarial Evaluation Matters

The purpose of adversarial evaluation is not simply to make attacks harder to detect.

It allows us to study the boundary between:

```text
What the model knows
```

and

```text
What the model can no longer recognize
```

A controlled experiment can gradually modify attack traffic and observe:

```text
Attack Variation
       ↓
Detection Confidence
       ↓
Novelty Score
       ↓
Security Assessment
       ↓
Learning Response
```

This lets us measure how Ovael behaves as an attack moves away from the patterns represented in its existing knowledge.

---

# Ovael's Detection Architecture

The detection system can be viewed as two specialized components rather than one model trying to solve every problem.

```text
                         OVAEL
                           |
                Network Traffic
                           |
                           ↓
                  Feature Extraction
                           |
              ┌────────────┴────────────┐
              |                         |
              ↓                         ↓
       Detection Model           Novelty Detection
              |                         |
       Known Behavior              Unknown Behavior
              |                         |
              └────────────┬────────────┘
                           ↓
                     Orchestrator
                           ↓
                      Risk Analysis
                           ↓
                  Security Assessment
```

The two paths provide different information.

The Detection Model focuses on **recognition**.

The Novelty component focuses on **familiarity**.

The Orchestrator brings those signals into a common context before the system produces its assessment.

---

# When the Models Disagree

An important part of the architecture is that disagreement is not necessarily treated as a failure.

Consider:

```text
Detection Model
→ Normal

Novelty Detection
→ Highly Unusual
```

This could indicate that the traffic does not match a known attack class but still looks significantly different from familiar behavior.

That disagreement becomes useful evidence.

The same applies when:

```text
Detection Model
→ Known Attack

Novelty Detection
→ Highly Unusual
```

This may indicate that the traffic resembles a known attack while also exhibiting behavior significantly different from previously observed examples.

Ovael therefore preserves both perspectives instead of reducing the entire event to one prediction.

---

# Orchestration

The Orchestrator is responsible for bringing the detection and novelty results together.

```text
Detection Result
       +
Novelty Result
       |
       ↓
Orchestrator
       |
       ↓
Combined Security Context
```

The exact mathematical or rule-based mechanism used to combine these signals remains a research decision.

Ovael does not assume that one signal should automatically override the other.

The goal is to preserve enough information for the next stage to make a meaningful assessment.

---

# Risk Analysis

Detection results alone do not necessarily provide enough context for a security decision.

Ovael therefore introduces a Risk Analysis stage.

Conceptually:

```text
Known-Class Prediction
        +
Detection Confidence
        +
Novelty Score
        +
Behavioral Evidence
        |
        ↓
   Risk Analysis
        |
        +---- Risk Score
        +---- Severity
        +---- Security Status
```

The exact risk formulation will be established through research and experimentation.

It is intentionally not treated as a fixed formula at this stage.

---

# Explainability

Ovael is intended to provide more than:

```text
Attack Detected
```

The system should eventually help answer:

```text
Why was this traffic considered suspicious?

Which features influenced the detection?

Was it recognized as a known attack?

Was it unusual even though it was not recognized?

How confident was the system?

What evidence supports the assessment?
```

This makes explainability an important part of turning model output into useful security information.

The exact explainability mechanism will be selected and evaluated during development.

---

# Controlled Network Environment

Ovael is intended to be evaluated in a controlled network environment.

The purpose is to generate, capture, modify, and analyze traffic under repeatable conditions.

```text
             Network Environment
                     |
          +----------+----------+
          |                     |
          ↓                     ↓
    Normal Traffic        Attack Traffic
          |                     |
          +----------+----------+
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

This allows experiments to be reproduced instead of relying only on static datasets.

---

# Research Evaluation

Ovael should not be evaluated only by asking:

> **"How accurate is the classifier?"**

A more important set of questions is:

```text
Can known attacks be detected reliably?

Can unfamiliar behavior be identified?

Can modified attacks escape known-class recognition?

Can novelty detection identify those changes?

Can genuine unknown attacks be separated from benign novelty?

Can validated discoveries improve future detection?

Does the system become more capable after learning?

How does performance change as traffic and workload increase?
```

These questions shift the evaluation from simple classification accuracy toward **adaptation and robustness**.

---

# The Ovael Learning Cycle

The long-term vision can be summarized as:

```text
             ┌──────────────────────┐
             │                      │
             ↓                      │
       Network Traffic              │
             ↓                      │
      Known Detection               │
             │                      │
             │              Unknown │
             │              Behavior│
             │                      ↓
             │              Novelty Detection
             │                      ↓
             │                 Investigation
             │                      ↓
             │                   Validation
             │                      ↓
             │                Confirmed Attack
             │                      ↓
             │                 Self-Learning
             │                      ↓
             └──────────── Model Update
                                    │
                                    ↓
                           Improved Detection
```

The system therefore has the potential to move from a static detector toward an **evolving detection system**.

---

# Research Questions

Ovael is ultimately built around several connected questions:

### Known Threat Detection

**How effectively can a supervised detection model recognize attacks represented in its training knowledge?**

### Unknown Threat Discovery

**Can novelty detection identify network behavior that falls outside that learned knowledge?**

### Adversarial Robustness

**What happens when known attacks are deliberately modified to appear different from their original representations?**

### Validated Self-Learning

**Can genuinely new attack behavior be validated and incorporated into future detection without blindly learning from false anomalies?**

### Continuous Improvement

**Can the system become better at recognizing future variations after learning from validated discoveries?**

---

# What Makes Ovael Different?

Ovael is not simply:

```text
Dataset
   ↓
Train Model
   ↓
Predict Attack
```

Instead, it explores an evolving cycle:

```text
             KNOWN
               ↓
             Detect
               ↓
        Attack Changes
               ↓
            UNKNOWN
               ↓
            Discover
               ↓
           Investigate
               ↓
            Validate
               ↓
             Learn
               ↓
             KNOWN
               ↓
        Better Detection
```

The interesting part is not only detecting an attack.

It is studying what happens **after the system encounters something it does not know**.

---

# Research Foundation

Ovael's direction is informed by research covering:

* machine-learning-based intrusion detection
* known vs. unseen attack detection
* novelty/anomaly detection
* explainable security analysis
* multi-agent security systems
* adaptive intrusion detection
* robustness against modified attack behavior

These areas provide the foundation for the research questions Ovael intends to investigate.

The specific algorithms, datasets, learning mechanisms, and implementation techniques will be selected through experimentation rather than assumed in advance.

---

# Development Philosophy

Ovael will be developed incrementally.

We will first build a small, understandable detection pipeline.

Then we will introduce:

```text
Detection
   ↓
Novelty
   ↓
Orchestration
   ↓
Risk Analysis
   ↓
Validation
   ↓
Self-Learning
   ↓
Adversarial Evaluation
   ↓
Scalable Deployment
```

Infrastructure will be introduced when the system actually requires it.

We do not intend to introduce distributed systems, queues, containers, or cloud infrastructure simply because they are associated with scalable architectures.

The goal is to **measure first and scale deliberately**.

---

# The Long-Term Vision

The long-term goal of Ovael is to investigate whether network threat detection can move beyond a static model trained once on a fixed collection of attacks.

Instead, we want to explore a system that can:

```text
Recognize what it knows
          ↓
Notice what it does not know
          ↓
Investigate unfamiliar behavior
          ↓
Validate genuine threats
          ↓
Learn from validated discoveries
          ↓
Improve future detection
```

A system where an unknown attack does not necessarily remain unknown forever.

---

# The Question Behind Ovael

> ### **Can a network security system detect what it already knows, recognize when an attack has changed beyond its knowledge, validate genuinely new threats, and learn from those discoveries to become better at detecting what comes next?**

Ovael is our attempt to investigate that question.

Not by assuming that every anomaly is malicious.

Not by assuming that a classifier will recognize every future attack.

And not by blindly teaching the system everything it encounters.

**Ovael explores the possibility of a security system that can discover, validate, and evolve.**
