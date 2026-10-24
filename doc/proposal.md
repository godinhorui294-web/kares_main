# KARES: A Knowledge-Driven Framework for Autonomous Algorithm Discovery in Scheduling

> This document is the project proposal. Formulas are given as code blocks or inline expressions; figures and tables are marked as placeholders.

---

## Abstract

The efficiency of optimization systems depends heavily on expert-designed algorithms, and innovation in this space iterates slowly. LLM-driven AutoResearch approaches have opened a new path toward automatic algorithm discovery, yet existing methods commonly lack effective injection of external domain knowledge, correct guidance on the direction of algorithmic improvement, and sustained, stable code generation — three limitations that jointly constrain the efficiency of autonomous algorithm evolution. This paper proposes KARES, a framework that introduces and structurally accumulates domain knowledge through a **self-evolving knowledge base**, converts numerical feedback into clear improvement guidance from complementary perspectives via a **dual-track reflection mechanism**, and performs multi-dimensional validation with proactive repair on candidate code through a **mechanical barrier**, forming an accumulative closed loop of "reflect — retrieve — generate — verify — sediment".

**Keywords**: scheduling algorithms; automatic algorithm discovery; large language models; knowledge-driven evolution; combinatorial optimization

---

## 1. Introduction

Scheduling problems pervade manufacturing, logistics, and information services, and as application scenarios keep expanding, the demand for more efficient and robust scheduling algorithms grows ever more urgent. Yet the pace of algorithm research falls far behind demand growth, and the rapid development and continuous evolution of scheduling algorithms has become a central challenge in the field [1][2][3].

The root of this tension lies in the inherent mode of scheduling algorithm research. Scheduling is a typical family of NP-hard combinatorial optimization problems, and proposing a new algorithm usually requires human experts to draw on domain knowledge to conduct theoretical analysis, algorithm design, and extensive experimental validation. Under this mode, the journey from an initial idea to a validated, deployed algorithm often consumes enormous time, failing to meet the need for rapid algorithm iteration in practical settings.

In recent years, large language models (LLMs) have demonstrated strong capabilities in code generation, reasoning, and self-correction, opening a new technical path toward automated algorithm discovery. Representative works such as FunSearch [4], EoH [5], ReEvo [6], and LLMOA [7] have preliminarily validated the feasibility of LLMs automatically generating runnable scheduling heuristics. When confronting complex scheduling problems, however, existing methods face a **triple bottleneck**:

1. **Static knowledge boundary** — methods represented by FunSearch and AlphaEvolve rely on the LLM's internal knowledge, cannot dynamically introduce external information during iteration, and lack the capacity for continuous learning and knowledge growth.
2. **The semantic conversion problem for numerical feedback** — EoH drives search with fitness values alone and cannot convert numerical differences into improvement directions at the level of algorithm structure; ReEvo introduces reflection, but confines it within the population and fails to connect it with external knowledge.
3. **Unreliable code generation stalling autonomous experimentation** — LLM-generated scheduling code frequently exhibits dependency violations and resource mismatches, causing large fractions of candidates to be discarded before evaluation; the resulting scarcity of effective exploration samples creates a vicious cycle in which low-quality generation and wasted evaluation reinforce each other.

To address these problems, this paper proposes the KARES framework with three tightly coupled core mechanisms:

1. An **evolving knowledge base** organizes external literature and historical experimental experience in layers, endowing the system with the ability to retrieve and accumulate knowledge dynamically and thereby break the static knowledge boundary.
2. A **dual-track reflection mechanism** converts numerical feedback into reusable internal knowledge by horizontally comparing algorithm structures within a generation and vertically tracking evolutionary trajectories across generations, providing semantically grounded improvement directions for subsequent iterations.
3. A **mechanical barrier** performs syntactic, structural, and runtime validation with proactive repair on candidate algorithms, shifting from "filter after generation" to "guide during generation", markedly reducing wasted evaluations while ensuring the feasibility of generated code.

Together the three mechanisms form a complete closed loop: reflection drives retrieval, retrieval augments generation, and what the barrier verifies is sedimented back into the knowledge base, so that the system's cognition and generation capability keep growing across iterations.

This paper adopts the **UAV forest firefighting scheduling scenario** as the testbed. The scenario involves task sequence dependencies, UAV type matching, time windows, ammunition and flight range constraints, among others [8][9][10], posing a severe challenge to algorithm discovery capability. Experimental results show that the method improves upon the strongest comparison method, AlphaEvolve, by about 65.6% across 30 test instances, and outperforms EoH and ReEvo by about 127.9% and 126.8%, respectively. Ablation studies confirm the effectiveness of each core module, and analyses of the evolution process further reveal the internal mechanism behind the framework's sustained performance gains.

The remainder of this paper is organized as follows: Section 2 reviews related work; Section 3 presents the KARES framework together with its self-growing knowledge base, dual-track reflection mechanism, and mechanical barrier; Section 4 reports the experimental setup and results analysis; Section 5 concludes and discusses future research directions.

---

## 2. Related Work

### 2.1 The Evolution of Scheduling Algorithms

As a core topic in operations research and artificial intelligence, scheduling has accumulated more than 290,000 papers, reflecting the pressing demand for efficient scheduling methods in manufacturing, logistics, energy, and transportation. The expansion of this body of research, however, has not brought a proportional acceleration in algorithmic evolution, which remains slow along two dimensions: horizontal innovation and vertical improvement.

**Horizontal dimension**: new algorithm families emerge slowly. Exact algorithms (e.g., branch and bound) achieve theoretical optimality but, being constrained by NP-hardness, scale poorly to large instances [11]; heuristic rules (e.g., EDD, SPT) are simple to implement but have low performance ceilings and struggle with complex constraint settings. Facing these bottlenecks, metaheuristics emerged in concentration during the 1980s–1990s: genetic algorithms mimic natural selection [12]; simulated annealing adopts the Metropolis criterion to escape local optima probabilistically [13]; tabu search uses memory to avoid cycling [14]; ant colony optimization converges via positive feedback [15]; and particle swarm optimization [16] simulates socially learned global search. Yet each of these methods took 10–20 years from proposal to becoming a standard tool of the field.

**Vertical dimension**: the maturation of any single algorithm also spans a long improvement cycle. Reinforcement learning illustrates this well: Zhang and Dietterich first attempted reinforcement learning for job-shop scheduling in 1995 [17], but progress stalled on state-space explosion. Only in 2015 did the deep Q-network (DQN) combine deep learning with Q-learning [18], with proximal policy optimization (PPO) further improving stability and sample efficiency in 2017 [19] — more than two decades from first attempt to mature application of deep reinforcement learning.

The introduction of the Transformer architecture is even more typical: proposed in 2017 [20], its self-attention mechanism captures long-range sequential dependencies, and from 2024 it has been systematically adopted in scheduling, including Decision Transformer-enhanced neural local search [21], DGSS combining graph neural networks for cross-scale generalization [22], ReSched compressing FJSP into four-dimensional core features [23], HGT-Scheduler with heterogeneous graph Transformers [24], and Sequence-to-Schedule achieving millisecond-level inference [25]. Seven years elapsed from the Transformer's proposal to its application, and it remains in the exploration stage in scheduling.

In summary, the evolution of scheduling algorithms exhibits the dual predicament of **sparse horizontal innovation and sluggish vertical improvement**. The essence of this tension is that the human-expert-driven research paradigm has nearly exhausted its exploration efficiency over the design space of scheduling algorithms. Building an algorithm discovery system that can automatically digest literature, autonomously distill experience, and automatically validate code — reducing algorithm research to a standard workflow executable by LLMs — has therefore become the key path to breaking this bottleneck.

### 2. AI-Driven Algorithm Discovery

In recent years, AI-driven automated scientific research (AutoResearch) has advanced markedly [26][27][28][29][30], with studies extending across the full research life cycle including literature survey, hypothesis generation, and experimental validation [31][32][33][34][35][36]. In the specific direction of automatic algorithm discovery, large language models (LLMs) show great promise owing to their capabilities in code generation, reasoning, and self-correction [37][38][39].

Several representative studies have preliminarily validated the feasibility of LLM-assisted algorithmic innovation:

- **FunSearch** [4]: couples a pretrained LLM with a systematic evaluator and discovers constructions exceeding the previously best known results on extremal combinatorics problems through evolutionary program search; it has also been applied to improving job scheduling algorithms.
- **AlphaEvolve** [40]: an evolutionary coding agent that automatically generates and improves algorithms through an iterative "propose → test → optimize" process.
- **LLMOA** [7]: uses LLMs to automatically generate and optimize metaheuristics.
- **EoH** [5]: combines LLMs with evolutionary computation, providing a new evolutionary framework for automatic heuristic design.
- **ReEvo** [6]: treats large language models as hyper-heuristics and combines them with reflective evolution to automatically generate and iteratively optimize scheduling heuristics.

These methods each have strengths in automatic algorithm generation and iterative optimization, but none has yet systematically integrated **dynamic injection of external knowledge, semantic reflection mechanisms, and feasibility safeguards** into a unified framework. The KARES framework proposed in this paper builds on these works to further explore how sustained knowledge-base growth, the semantic guidance of dual-track reflection, and the proactive verification of a mechanical barrier can achieve efficient autonomous discovery of scheduling algorithms.

---

## 3. Method

### 3.1 Framework Overview

KARES uses an LLM as the algorithm generation core and a self-evolving knowledge base as its long-term memory. A dual-track reflection mechanism first produces structured summaries of the current algorithm pool and constructs knowledge retrieval queries; the system then retrieves relevant knowledge fragments from the knowledge base, which together with the current algorithm form the LLM's context. After the LLM generates a candidate algorithm, a mechanical barrier performs automatic validation and repair to yield an executable program. Performance evaluation results are fed back into the reflection mechanism, and new knowledge is sedimented back into the knowledge base, forming the iterative evolution loop of **"reflect — retrieve — generate — verify — sediment"**.

> **Figure 1: Overall architecture of the KARES framework** (placeholder)

Algorithm 1 gives the pseudocode of this closed-loop iterative process (notation in Table 1).

> **Table 1: Main notation used in Algorithm 1** (placeholder)

```
Algorithm 1: KARES closed-loop iteration (pseudocode)
Input: problem definition P, initial algorithm pool A0, knowledge base KB, iteration count T
Output: best algorithm a*
1:  for t = 1 to T do
2:      // Dual-track reflection
3:      Rh ← HorizontalReflection(A_{t-1})        // horizontal: within-generation structural comparison
4:      Rv ← VerticalReflection(history, W)        // vertical: cross-generation trajectory tracking
5:      q  ← Embed(Rh ⊕ Rv)                        // build retrieval query
6:      // Knowledge retrieval
7:      K  ← Retrieve(KB, q)                       // retrieve relevant knowledge subset
8:      // Generation
9:      c  ← LLM.Generate(P, A*_{t-1}, Rh, Rv, K)  // candidate algorithm
10:     // Mechanical barrier (evaluate — improve — verify)
11:     c' ← MechanicalBarrier(c, P)               // multi-dimensional validation and proactive repair
12:     // Diversity screening
13:     if not Duplicate(c', A_{t-1}) then
14:         A_t ← A_{t-1} ∪ {c'}
15:     // Evaluation
16:     f  ← Evaluate(c', P)
17:     // Sedimentation
18:     KB ← Sediment(KB, Rh, Rv, repair_logs)
19: end for
20: a* ← argmax_{a∈A_T} fitness(a)
```

### 3.2 Self-Evolving Knowledge Base

We construct a self-evolving knowledge base with a **four-layer progressive architecture** (Figure 1a) that provides traceable knowledge storage, structured induction, and dynamic weight updates.

1. **Raw data layer**: stores the full text of scientific literature and technical reports. The LLM may only perform read-only retrieval and citation on this layer; rewriting is forbidden, ensuring knowledge traceability and mitigating LLM hallucination.
2. **Practical experience layer**: collects three types of fine-grained raw feedback — environment logs from each iteration, the structured summary text output by the reflection mechanism (Section 3.3), and code validation and repair records (Section 3.4) — preserving the complete raw context for later induction.
3. **Structured knowledge layer**: takes inputs from the raw data layer and the practical experience layer and induces knowledge into a unified structured collection:

   ```
   K = { (d_i, s_i, v_i, sc_i) }
   ```
   where `d_i` is a natural-language description distilled by the LLM from the core content of the source literature or from experimental experience; `s_i` is the source citation recording the knowledge's provenance; `v_i` is the effectiveness score, initialized by the LLM according to the strength of the source conclusions and the experimental results, and subsequently updated with an exponential moving average, adjusted dynamically according to whether each citation leads to a better algorithm; and `sc_i` is the scope of applicability, describing the scheduling scenario types to which the knowledge applies.

4. **Rule layer**: contains meta-rules such as "every knowledge unit must record its source literature DOI or experiment round" and "generating code containing undefined variables is forbidden". When the LLM is invoked, these rules are prepended as a system prompt to guarantee the regularity and consistency of knowledge sedimentation. The initial rules are pre-written from the general constraints of scheduling problems and remain static during system operation; new rules may be appended to the rule file after manual review.

**Knowledge retrieval**: the system first computes the cosine similarity between the query embedding and each entry's description embedding, then ranks entries by a weighted combination of the effectiveness score and the match with the current task scenario (see Appendix A). Retrieval results are randomly sampled to form the reference knowledge subset for the generation stage. Through this four-layer design, the knowledge base is simultaneously traceable and capable of growth, so that every algorithm design by the LLM builds on the starting point of past experiments.

### 3.3 Dual-Track Reflection Mechanism

We propose a **dual-track reflection mechanism** that produces structured summaries of each round of experimental results and outputs improvement directions at the semantic level. The mechanism comprises two complementary branches, horizontal reflection and vertical reflection, which respectively summarize within-generation design patterns and cross-generation evolutionary regularities.

> **Figure 2: Dual-track reflection mechanism** (placeholder)

**Horizontal reflection** takes the current algorithm pool `A_{t-1}` and the fitness of each candidate as input. It performs structured comparisons along dimensions such as task-ordering strategy and constraint handling, inducing three categories of information: (1) design features worth preserving; (2) design flaws to avoid; and (3) actionable improvement suggestions. The result is denoted the horizontal reflection output `Rh`.

**Vertical reflection** takes the current best solution and the historical best trajectory as input (`W` is the retention window size); the system invokes the LLM to analyze the improvement relations between the current best and recent historical optima, identifying structural features persistently retained across generations. The result is denoted the vertical reflection output `Rv`.

The outputs of horizontal and vertical reflection are encoded by a text embedding model to construct the retrieval query:

```
q = Embed(Rh ⊕ Rv)                                   (2)
```

Meanwhile, the text of `Rh` and `Rv` is written directly into the next iteration's prompt as explicit constraints for candidate generation (prompt templates in Appendix B).

The system records, for each piece of cited knowledge, the fraction of subsequently generated algorithms that surpass the current best, as the raw basis for updating that knowledge's effectiveness score `v_i`.

### 3.4 The Mechanical Barrier: A Verify-Repair Closed Loop

KARES employs a mechanical barrier to perform syntactic, constraint, and runtime validation with proactive repair on candidate code. The architecture consists of three sequentially linked modules — **evaluation, improvement, and verification** (Figure 3) — that process candidate code in an iterative "inspect — repair — re-inspect" flow (full prompts and output examples in Appendix B).

> **Figure 3: The Mechanical Barrier framework** (placeholder)

- **Evaluation Agent**: performs structured inspection of the candidate code covering three dimensions — syntax (AST parsing), constraints (hard constraints such as task dependencies and resource matching), and runtime behavior (memory usage and execution time) — and outputs a standardized evaluation report:

  ```
  Report = { (err_type_k, loc_k, fix_suggestion_k) }
  ```
  where `err_type_k` labels the error category, `loc_k` locates the problematic line, and `fix_suggestion_k` provides a repair suggestion.

- **Improvement Agent**: applies targeted code modifications based on the evaluation report, outputting a repaired version together with a repair note.

- **Verification Agent**: compares AST structures to ensure the algorithm's structure remains consistent before and after repair, preventing the repair process from breaking core logic, and runs test instances in a dynamic sandbox to confirm constraint satisfaction and adequate performance.

These three agents constitute a **bounded repair loop** (Algorithm 2): given the code `c` under inspection, each repair attempt begins with the evaluation module producing a report; if `verdict = PASS`, `c` is returned directly as the feasible solution; if `verdict = FAIL` and the attempt count is below the maximum repair rounds (3 in this paper), the improvement module produces `c'`, which the verification module confirms. If verification passes, `c'` replaces `c` for the next inspection round; if it fails, the newly found errors are merged into the original report for the improvement module to try again. When consecutive repair rounds all fail, the candidate is deemed unrepairable and processing terminates.

The inspection and repair records of the mechanical barrier are simultaneously sedimented into the knowledge base, forming a positive cycle: unrepairable failure cases are induced by the system into **prohibitive constraints** written in a fixed format into subsequent iterations' LLM system prompts, so that the model actively avoids known faulty structures at generation time; successfully repaired cases (problem plus corresponding solution) are stored in the knowledge base to sharpen subsequent repairs.

**Diversity screening**: once a candidate program passes the mechanical barrier's feasibility verification, the system further performs diversity screening to prevent the algorithm pool from losing exploration efficiency to duplicate structures. The screening relies on **two-level hash fingerprints**:

- **Structure-level hash**: computed on the normalized abstract syntax tree of the code, reflecting framework-level structure such as operator types and selection strategy;
- **Logic-level hash**: applied only when the structure-level hashes match, computed by serializing the concrete execution logic inside the operators, reflecting substantive implementation differences.

The system compares the current candidate's hashes against every record in the algorithm pool: if both levels match, the candidate is judged an exact duplicate and discarded; otherwise it is admitted to the pool for subsequent evaluation. This screening provides deterministic duplicate detection at negligible computational cost, complementing the barrier's feasibility verification — the former safeguards structural novelty of candidate programs, the latter their executability.

---

## 4. Experiments

The UAV forest firefighting scheduling problem, with its vast discrete decision space and tightly coupled constraint structure, provides a highly challenging test scenario for examining LLM-driven autonomous algorithm discovery. The problem combines task sequence dependencies, heterogeneous UAV matching, time windows, ammunition and flight range constraints, and other requirements, and unites NP-hardness with a clear real-world application background [8][9][10][41].

### 4.1 Problem Definition

#### 4.1.1 Scenario Overview

Multiple fires break out across a forest region. The ground command center operates a heterogeneous UAV fleet comprising **scout UAVs** and **fighter UAVs**. Each fire point requires three sequential tasks — **reconnaissance, firefighting, and reinspection** — where the firefighting task carries a time window constraint while reconnaissance and reinspection have none. UAVs operate in 3D space at a constant cruising speed subject to a maximum flight range; fighter UAVs are additionally constrained by initial ammunition and may return to the base to refill after depletion. A fire point is considered fully extinguished, earning the corresponding protection value reward, only when all three of its tasks complete successfully.

#### 4.1.2 Mathematical Model

The quality of a scheduling plan is quantified by a composite fitness function designed to maximize total rescue reward and minimize operating cost under strict satisfaction of all hard constraints. The fitness consists of a **reward term, cost terms, and a penalty term**.

> **Table 2: Main notation** (placeholder)

**(1) Reward term**: if all three tasks of fire point `j` are executed successfully, the fire point is fully extinguished and yields a base reward proportional to its protection value `V_j` and fire level `HP_j`. Summing over all fully extinguished fire points gives the total reward:

```
R = Σ_j 3 · V_j · HP_j                                (3)
```

**(2) Cost terms** — actual scheduling incurs two kinds of costs:

- **Delay cost**: if the actual start of a fire point's firefighting task is later than its deadline, a delay cost accrues, defined as the sum of overtime penalties over all firefighting tasks:

  ```
  C_delay = Σ_j max(0, start_j − end_j) · 10
  ```

- **Flight cost**: the total flight range consumed by all UAVs while executing tasks, defined as the product of the total flight range over all UAVs and the unit flight cost coefficient:

  ```
  C_fly = (Σ_i distance_i) · 3
  ```

**(3) Penalty term**: a schedule must satisfy three classes of hard constraints — ① **sequential dependency**: the three tasks of each fire point must be executed strictly in the order "reconnaissance → firefighting → reinspection"; ② **type matching**: reconnaissance and reinspection tasks may only be assigned to scout UAVs, and firefighting tasks only to fighter UAVs; ③ **resource constraints**: no UAV may exceed its maximum flight range, and a fighter UAV executing a firefighting task must hold remaining ammunition of at least `HP_j`. Each violation of these hard constraints is counted and penalized at a fixed rate:

```
P = N_violation · 1000
```

**(4) Composite fitness function**:

```
F = R − C_delay − C_fly − P                          (4)
```

### 4.2 Experimental Setup

#### 4.2.1 Test Set

To evaluate algorithm performance, 30 test instances were randomly generated with parameters drawn from the ranges in Table 3: the number of fire points, protection values, and fire levels were sampled equiprobably; time window parameters were uniformly sampled; and the numbers of scout and fighter UAVs and maximum flight ranges were fixed as in Table 3. The reward coefficient, delay penalty coefficient, flight cost coefficient, and hard constraint penalty strength were all set to the fixed values in Table 3. All instances were generated with a fixed random seed (`seed=42`) for reproducibility.

> **Figure 4: The forest firefighting UAV mission planning problem** (placeholder)
> **Table 3: Instance generation parameters** (placeholder)

#### 4.2.2 Evaluation Metrics

To quantitatively assess KARES's optimization performance and generalization, the following core metrics are defined (all computed on the same 30 test instances):

1. **Average fitness**: `AvgF = (1/N) Σ_k F_k`, reflecting average performance across instances; positively correlated with the value. `(7)`
2. **Improvement rate**: `Impr = (AvgF_method − AvgF_baseline) / |AvgF_baseline|`, measuring the gain over a baseline. `(8)`
3. **Generalization**: measured by the standard deviation `σ` and the coefficient of variation `CV = σ / AvgF`; smaller `CV` means smaller cross-instance performance fluctuation and stronger generalization. `(9)`
4. **Innovativeness**: `N(s) = (1 − sim(s, K_0)) · Δfitness(s)`, where `K_0` is the initial literature collection, `sim` is the cosine similarity between the embedded structured description of the strategy and the knowledge summaries in `K_0`, and `Δfitness` is the difference between the generation-best fitness after the strategy was confirmed by dual-track reflection as the dominant generational innovation and the previous generation's best. `(10)`
5. **Statistical significance testing**: pairwise comparisons use the paired Wilcoxon signed-rank test, supplemented by a binomial sign test to determine whether the frequency with which KARES outperforms the strongest comparison method across repeated runs is significant; the significance level is uniformly `α=0.05`.

#### 4.2.3 Comparison Methods and Experimental Environment

**(1) Representative baseline algorithms in the knowledge base** (8 methods):

- **BRKGA**: biased random-key genetic algorithm [42]
- **Hyper-Heuristic DPSO**: discrete PSO transplanted into a hyper-heuristic framework [43]
- **MPQGA**: multiple priority queueing genetic algorithm [44]
- **Quantum-Behaved PSO**: quantum-behaved PSO [45]
- **IGA**: improved genetic algorithm [46]
- **GA-ACO**: hybrid GA and ACO algorithm [47]
- **PCRT-GA**: hybrid heuristic–genetic algorithm [48]
- **Adaptive jDE**: self-adaptive differential evolution variant [49]

**(2) State-of-the-art LLM-driven algorithm discovery frameworks**:

- **EoH** [5], **ReEvo** [6], **LLMOA** [7], **AlphaEvolve** [40]

All experiments ran in the same environment: Python 3.11, Ubuntu 22.04.3 LTS, Intel Xeon E5-2680 v4 (56 threads, 2.40 GHz), 64 GB RAM, no GPU acceleration; LLM API calls were made over the network.

### 4.3 Comparison Results

#### 4.3.1 Comparison with Knowledge-Base Baseline Algorithms

KARES achieves the best final average fitness: about 29.3% better than the strongest baseline, Quantum-Behaved PSO (5107.33), and more than 329.4% better than the weakest baseline, Adaptive jDE (1537.71). In terms of stability, KARES has a standard deviation of 915.37 with a small coefficient of variation and limited performance fluctuation, whereas Adaptive jDE has a standard deviation of 2376.17 with a CV as high as 1.54, reflecting severe failure on some instances. KARES completes its rapid climb within about 20,000 evaluations and then enters a plateau of convergence, while the convergence curves of all baselines flatten in the middle-to-late stages.

> **Figure 5: Convergence curves of the optimizers** (placeholder)

#### 4.3.2 Comparison with LLM-Driven Methods

> **Figure 6: Comparison with other LLM-driven algorithms** (placeholder)
> **Table 4: Resource consumption of each method** (placeholder)

KARES has the most compact box, with an interquartile range significantly smaller than all comparison methods. Its average fitness is 6,602.23 — 65.6% above the runner-up AlphaEvolve (3,986.90) — and it improves upon EoH, ReEvo, and LLMOA by about 127.9%, 126.8%, and 133.8%, respectively. Regarding resource efficiency, KARES makes the fewest LLM calls of all methods (136), indicating that the dual-track reflection mechanism effectively reduces wasted generation. Its total input tokens (304k) exceed those of AlphaEvolve (112k) and ReEvo (164k), mainly due to the knowledge retrieval assembly in dual-track reflection and the multi-round repair verification of the mechanical barrier.

Statistical significance: across 20 independent repeated runs, the Wilcoxon test between KARES and the strongest comparison method, AlphaEvolve, yields `p < 0.01`; the binomial sign test shows KARES outperforming AlphaEvolve in all 20 runs. These results strongly demonstrate that KARES's performance advantage is not random fluctuation.

### 4.4 Interpretation of the Operating Mechanism

#### 4.4.1 Evolution Tree Analysis

> **Figure 7: Complete evolution trajectory of a typical single KARES run** (placeholder)

KARES's evolution can be divided into three phases:

- **Initial phase**: fitness starts in a low band around 3,784. The LLM relies on remedial measures such as topological-sort initialization and length checking to keep code legal, and much of the evaluation budget is consumed by ineffective loops.
- **Second phase**: fitness climbs rapidly from 3,784 to 6,185, and constraint handling shifts from post-generation external repair to embedding at generation time. Horizontal reflection identifies that "constraint-embedded" individuals have a markedly higher feasible-solution ratio, and vertical reflection confirms that this pattern is persistently retained across generations; it is ultimately sedimented as a constraint-first design principle.
- **Final phase**: fitness plateaus around 6,558. The LLM integrates constraint embedding, population cooperation, and adaptive control into a unified framework, and the generation strategy shifts from isolated local improvements to the coordinated fusion of multiple mechanisms.

This evolutionary rhythm exhibits a "**feasibility before optimality**" path — a spontaneous response to the problem's veto-style hard constraints.

#### 4.4.2 Citation Effectiveness of Knowledge Retrieval

> **Figure 8: Heat map of technical strategies** (placeholder)

Knowledge about deterministic dependency handling and constraint repair is cited most frequently; their shared feature is directly addressing the core bottlenecks of the UAV scheduling problem (task sequence dependencies and heterogeneous UAV matching). By contrast, local-search knowledge (Tabu, 2-opt) is cited rarely and yields poor guidance — the hard constraints in UAV scheduling are mandatory, and local micro-adjustments easily destroy already satisfied global dependencies. This indicates that the value of retrieved knowledge depends not on its importance in the literature but on its fit with the constraint structure of the problem at hand.

### 4.5 Ablation Studies

#### 4.5.1 Ablation of Core Modules

> **Figure 9: Ablation studies** (placeholder)

- Removing the self-evolving knowledge base drops performance to 4618.51 (a 30.0% decrease);
- Removing the dual-track reflection mechanism drops it to 4880.2 (a 26.1% decrease);
- The two act synergistically — removing either module alone yields lower performance than the complete system.

> **Figure 10: Example of dual-track reflection and knowledge retrieval working together** (placeholder)

#### 4.5.2 Effectiveness Analysis of the Mechanical Barrier

> **Table 5: Mechanical barrier repair statistics** (placeholder)

Repair success rates across the three dimensions of syntax, constraints, and performance range between 60% and 81.8%; error patterns are relatively fixed (undefined variables, dependency-order violations, insufficient convergence speed) and can be repaired programmatically via AST transformations or parameter adjustments. The success rate of runtime verification (40%) is markedly lower than the other dimensions, and it intercepts the fewest cases (5) — runtime errors (memory overflow, infinite loops) are triggered highly dependently on the boundary conditions of the input data, and their repair often exceeds what the mechanical barrier's static analysis and sandbox verification can handle; such failures should be stored in the knowledge base and actively avoided by the LLM in subsequent iterations.

### 4.6 Algorithmic Innovation Capability

> **Figure 11: Scatter plot of innovative knowledge** (placeholder)

The strategies produced by the experiments show a markedly uneven distribution across the two dimensions of semantic similarity and performance gain:

- **High-innovation zone** (`N(s) > 0.1`): contains only **Fire Block Construction** — encapsulating the "reconnaissance — firefighting — reinspection" triad into an indivisible atomic scheduling block with block-level ordering driven by fire level; semantic similarity 0.32 with a 30.2% performance gain;
- **Mid-high innovation zone** (`N(s) ∈ [0.05, 0.1]`): contains Structure-level Adaptation (similarity 0.428, gain 13.5%) and Boundary Reflect Mutation + 1-Point Crossover (similarity 0.437, gain 12.9%);
- The remaining strategies have `N(s) < 0.05`, manifesting as direct transplantation of retrieved knowledge or minor adjustments.

KARES's innovation does not rely on random exploration alone: under the continuous filtering of the reflection mechanism, low-value paths are progressively suppressed while high-value patterns are reinforced across generations, driving the LLM to evolve from directly transplanting retrieved knowledge toward domain-specific reconstruction.

---

## 5. Conclusion

This paper presented KARES, a knowledge-driven method for autonomous algorithm discovery in scheduling. Its core idea is to recast automatic algorithm discovery from blind code search into **knowledge-driven closed-loop reasoning**: a self-evolving knowledge base dynamically accumulates external knowledge and historical experience; a dual-track reflection mechanism converts vague numerical feedback into structured semantic improvement directions; and a mechanical barrier front-loads feasibility verification. The three operate synergistically to form the accumulative closed loop of "reflect — retrieve — generate — verify — sediment".

Experiments on the UAV forest firefighting scheduling problem show that KARES significantly outperforms existing mainstream comparison methods — both classical heuristics and state-of-the-art LLM-driven algorithm discovery frameworks — in both solution quality and algorithmic innovation. During the experiments the system autonomously discovered dozens of original scheduling strategies superior to existing methods in the knowledge base, including Fire Block Construction and Structure-level Adaptation.

Analysis of the evolution trajectories also reveals the applicable boundary of the proposed knowledge-driven paradigm: on small- to medium-scale instances, the system exhibits stable convergence and consistent performance gains. Future work will focus on three directions:

1. **Dynamic scenario extension**: extending KARES to real-time scheduling with stochastic disturbances and event-driven arrivals, exploring incremental updating and fast retrieval for the knowledge base;
2. **Enhanced reflection**: introducing a multi-agent debate framework, using cross-dialogue of "generate — critique — verify" to deepen reflection and improve the originality of hypotheses;
3. **Secondary strategy optimization**: adaptively tuning generated strategies with reinforcement learning, using behavior to dynamically select improvement directions.

---

## References

[1] A. Momenikorbekandi and T. Kalgovsky, "Intelligent Scheduling Methods for Optimisation of Job Shop Scheduling Problems in the Manufacturing Sector: A Systematic Review," *Electronics*, vol. 14, no. 8, p. 1663, 2025.
[2] H. Hudaifah et al., "Human-aware scheduling for sustainable manufacturing: A review of dynamic job shop scheduling in the era of Industry 5.0," *Robot Comput-Integr Manuf*, vol. 98, 2026.
[3] C. Ngwu, Y. Liu, and R. Wu, "Reinforcement learning in dynamic job shop scheduling: a comprehensive review," *J. Intell. Manuf.*, vol. 37, no. 3, 2026.
[4] B. Romera-Paredes et al., "Mathematical discoveries from program search with large language models," *Nature*, vol. 625, no. 7995, pp. 468–475, 2024.
[5] F. Liu et al., "Evolution of Heuristics: Towards Efficient Automatic Algorithm Design Using Large Language Model," *ICML*, 2024.
[6] H. Ye et al., "ReEvo: Large Language Models as Hyper-Heuristics with Reflective Evolution," *NeurIPS*, 2024.
[7] R. Zhong, A. G. Hussien, J. Yu, and M. Munetomo, "LLMOA: A novel large language model assisted hyper-heuristic optimization algorithm," *Adv Eng Inf.*, vol. 64, 2025.
[8] İ. Sadati, "An efficient matheuristic integration with benders decomposition for unmanned aerial vehicle routing problem in forest fire surveillance," *Comput. Ind. Eng.*, vol. 204, 2025.
[9] H. Vo et al., "A Comparative Analysis of Task Allocation Strategies for Resource-Constrained Multi-Agent Drone Swarms in Wildfire Response," *IEEE ICNSC*, 2025.
[10] E. Dasdemir, E. Jose, and R. Batta, "Scheduling and routing with degradation-triggered job arrivals: An application to forest firefighting with an unmanned aerial vehicle fleet," *Eur. J. Oper. Res.*, vol. 330, no. 3, 2026.
[11] A. H. Land and A. G. Doig, "An Automatic Method of Solving Discrete Programming Problems," *Econometrica*, vol. 28, no. 3, 1960.
[12] L. Davis, "Job Shop Scheduling with Genetic Algorithms," *ICGA*, 1985.
[13] S. Kirkpatrick, C. D. Gelatt, and M. P. Vecchi, "Optimization by Simulated Annealing," *Science*, vol. 220, no. 4598, 1983.
[14] F. Glover, "Future paths for integer programming and links to artificial intelligence," *Comput. Oper. Res.*, vol. 13, no. 5, 1986.
[15] M. Dorigo, V. Maniezzo, and A. Colorni, "Ant system: optimization by a colony of cooperating agents," *IEEE Trans. SMC-B*, vol. 26, no. 1, 1996.
[16] J. Kennedy and R. Eberhart, "Particle swarm optimization," *ICNN*, 1995.
[17] W. Zhang and T. G. Dietterich, "A Reinforcement Learning Approach to job-shop Scheduling," *IJCAI*, 1995.
[18] V. Mnih et al., "Human-level control through deep reinforcement learning," *Nature*, vol. 518, no. 7540, 2015.
[19] J. Schulman et al., "Proximal Policy Optimization Algorithms," arXiv:1707.06347, 2017.
[20] A. Vaswani et al., "Attention is All you Need," *NeurIPS*, 2017.
[21] C. W. de Puiseau et al., "Decision Transformer for Enhancing Neural Local Search on the Job Shop Scheduling Problem," arXiv:2409.02697, 2024.
[22] Z. Yuan et al., "Solving Size-Agnostic Job Shop Scheduling Problems Like GPT Speaks," *IEEE CASE*, 2024.
[23] X. Xiao, C. Zhang, W. Song, and Z. Cao, "RESCHED: Rethinking Flexible Job Shop Scheduling from a Transformer-based Architecture with Simplified States," *ICLR*, 2025.
[24] B. Soykan, "HGT-Scheduler: Deep Reinforcement Learning for the Job Shop Scheduling Problem via Heterogeneous Graph Transformers," arXiv:2603.06777, 2026.
[25] Z. Wen, P. Fu, H. Li, and C. Hu, "Sequence-to-schedule: A pure transformer scheduler for real-time resource management," *Eng. Appl. Artif. Intell.*, vol. 181, 2026.
[26] J. Wei et al., "From AI for Science to Agentic Science: A Survey on Autonomous Scientific Discovery," arXiv, 2025.
[27] S. Yang et al., "End-to-end autonomous scientific discovery on a real optical platform," arXiv:2604.27092, 2026.
[28] K. Lin et al., "SciDER: Scientific Data-centric End-to-End Researcher," arXiv:2603.01421, 2026.
[29] G. Ahn et al., "MIND: AI Co-Scientist for Material Research," arXiv:2604.13699, 2026.
[30] L. Zhou et al., "Autonomous Agents for Scientific Discovery," arXiv:2510.09901, 2025.
[31] G. Tie, P. Zhou, and L. Sun, "A Survey of AI Scientists," arXiv:2510.23045, 2026.
[32] G. Tie et al., "AutoResearch AI: Towards AI-Powered Research Automation for Scientific Discovery," arXiv:2605.23204, 2026.
[33] H. Jiang et al., "HypoChainer: A Collaborative System Combining LLMs and Knowledge Graphs for Hypothesis-Driven Scientific Discovery," *IEEE TVCG*, vol. 32, no. 01, 2026.
[34] J. Baek et al., "ResearchAgent: Iterative Research Idea Generation over Scientific Literature with LLMs," *NAACL*, 2025.
[35] K. Ding et al., "SciToolAgent: a knowledge-graph-driven scientific agent for multitool integration," *Nat. Comput. Sci.*, vol. 5, no. 10, 2025.
[36] S. Eger et al., "Transforming Science with Large Language Models: A Survey," arXiv:2502.05151, 2025.
[37] F. Liu et al., "A Systematic Survey on Large Language Models for Algorithm Design," *ACM Comput. Surv.*, vol. 58, no. 8, 2026.
[38] X. Wu et al., "Evolutionary Computation in the Era of Large Language Model: Survey and Roadmap," *IEEE Trans. Evol. Comput.*, vol. 29, no. 2, 2025.
[39] C. Wang et al., "When Large Language Models Meet Evolutionary Algorithms: Potential Enhancements and Challenges," *Research*, vol. 8, 2025.
[40] A. Novikov et al., "AlphaEvolve: A coding agent for scientific and algorithmic discovery," arXiv:2506.13131, 2025.
[41] J. Zhang, Y. Cui, and J. Ren, "Dynamic Mission Planning Algorithm for UAV Formation in Battlefield Environment," *IEEE Trans. Aerosp. Electron. Syst.*, vol. 59, no. 4, 2023.
[42] J. F. Gonçalves, M. G. Resende, and J. J. Mendes, "A biased random-key genetic algorithm with forward-backward improvement for the resource constrained project scheduling problem," *J. Heuristics*, vol. 17, no. 5, 2011.
[43] M. Alinia Ahandani et al., "Hybrid particle swarm optimization transplanted into a hyper-heuristic structure for solving examination timetabling problem," *Swarm Evol. Comput.*, vol. 7, 2012.
[44] Y. Xu, K. Li, T. T. Khac, and M. Qiu, "A Multiple Priority Queueing Genetic Algorithm for Task Scheduling on Heterogeneous Computing Systems," *IEEE HPCC*, 2012.
[45] X. Kong, J. Sun, B. Ye, and W. Xu, "An Efficient Quantum-Behaved Particle Swarm Optimization for Multiprocessor Scheduling," *ICCS*, 2007.
[46] Q. Lihong and L. Shengping, "An improved genetic algorithm for integrated process planning and scheduling," *Int. J. Adv. Manuf. Technol.*, vol. 58, no. 5, 2012.
[47] Y. Dai, Y. Lou, and X. Lu, "A Task Scheduling Algorithm Based on Genetic Algorithm and Ant Colony Optimization Algorithm with Multi-QoS Constraints in Cloud Computing," *IHMSC*, 2015.
[48] M. I. Daoud and N. Kharma, "A hybrid heuristic–genetic algorithm for task scheduling in heterogeneous processor networks," *J. Parallel Distrib. Comput.*, vol. 71, no. 11, 2011.
[49] J. Brest et al., "Self-Adapting Control Parameters in Differential Evolution," *IEEE Trans. Evol. Comput.*, vol. 10, no. 6, 2006.

---

## Appendix

### A. Hyperparameter Table (placeholder)

### B. Prompt Templates

The prompt templates live in the project's `prompts/` directory, organized by stage:

- `prompts/system/system_prompt.md` — system prompt and rule-layer meta-rules
- `prompts/reflection/horizontal_reflection.md` — horizontal reflection
- `prompts/reflection/vertical_reflection.md` — vertical reflection
- `prompts/generation/algorithm_generation.md` — candidate algorithm generation
- `prompts/barrier/evaluation.md` — evaluation Agent
- `prompts/barrier/improvement.md` — improvement Agent
- `prompts/barrier/verification.md` — verification Agent

### C. Supplementary Results (TSP Generalization)

To assess KARES's generalization across different combinatorial optimization problems, supplementary experiments were conducted on the standard TSPLIB benchmark. TSP involves only route-order constraints and differs structurally from UAV firefighting scheduling (which carries multiple hard constraints such as task dependencies and resource matching), making it useful for examining the framework's general algorithm discovery capability across problem types. KARES used exactly the same hyperparameter configuration as in the main experiments on TSP, without any problem-specific tuning.

> **Table C.1: KARES on the standard TSPLIB benchmark** (placeholder)

KARES attains the best results on all instances, with an average optimality gap of 0.03%, markedly better than ReEvo (10.9%) and EoH (15.7%). By instance size, KARES is especially stable on small and medium instances (eil51 through ch130) while maintaining low gaps on the larger instances (d493, ts225), validating the method's generalization across problem scales.
