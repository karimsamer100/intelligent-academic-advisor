# Local Intelligent Academic Advisor
## Master Project Context & Development Kickoff
**Version:** 2.0  
**Status:** Working Master Context  
**Team Size:** 5  
**Team Members:** Karim (Team Lead), Omar, Youssef, Ahmed, Karim  
**Primary Focus:** Academic Advising  
**Secondary Focus:** Selected Student Affairs informational support  
**Initial Academic Scope:** Computer-related program, Regulations 18 and 23  

---

# 1. Project Summary

The project is a **Local LLM-Based Intelligent Academic Advising System** designed to help university students make safer, more personalized academic decisions.

The system is not intended to be only a chatbot that reads university PDFs.

It combines:

- A **Local LLM** for natural conversation, intent understanding, missing-information questions, routing, and explanation.
- A **verified academic planning engine** for course eligibility, prerequisite analysis, course comparison, dependency analysis, academic-delay detection, and multi-semester planning.
- **Structured academic data** for rules and calculations.
- **RAG** for official textual information, regulations, policies, and selected Student Affairs questions.
- **Student academic profiles/history** for personalization.
- **Human advisor escalation and handoff** for unsupported or exceptional cases.

The system should behave as an **academic decision-support platform**, not as an unrestricted generative chatbot.

---

# 2. Current Project Status

## Completed / Available

- Official PDFs for **Regulations 18 and 23** have been collected.
- Course trees, prerequisites, regulations, credit-hour rules, electives, mandatory-course information, and related academic documents are available in varying forms.
- A student survey has been created and distributed.
- A meaningful number of survey responses has already been collected.
- The high-level project architecture has been agreed.
- The supervisor has given additional requirements and direction.
- The project team currently consists of five members.

## Not Yet Implemented

- Unified structured academic dataset.
- Verified academic rules store.
- Academic Planning Engine.
- RAG ingestion/retrieval pipeline.
- Local LLM integration.
- Student profile system.
- Advisor-side functionality.
- Track recommendation.
- End-to-end web application.
- Formal evaluation dataset / golden test cases.

---

# 3. Locked Product Direction

The following points should be treated as the current product direction unless explicitly changed later.

## 3.1 Primary Product

The core product is an **Academic Advisor**.

It should help students with:

- Course eligibility.
- Prerequisites.
- Course selection.
- Course comparison.
- Academic progress.
- Future course dependencies.
- Academic-delay risk.
- Multi-semester planning.
- Special academic situations.
- Personalized recommendations.
- Track / specialization guidance.
- Explanation of recommendations.

## 3.2 Secondary Product Capability

The system may answer selected **Student Affairs informational questions** such as:

- Required documents.
- Standard academic procedures.
- Registration-related rules.
- Add/drop information.
- General administrative academic policies.

This is a secondary capability and should not dominate the project.

## 3.3 Tutor

A full educational tutor is **not part of the initial core**.

It may be added later only after the Academic Advisor is stable.

---

# 4. Supervisor Updates

The supervisor added several important requirements and directions.

## 4.1 Student History-Based Personalization

The system should use the student's academic history when making recommendations.

Relevant history may include:

- Completed courses.
- Previous grades.
- Failed or repeated courses.
- GPA.
- Current registered courses.
- Academic load.
- Progress through prerequisite chains.
- Academic standing.
- Past academic decisions when relevant.

This history should affect recommendations instead of treating every student the same.

## 4.2 Track / Specialization Recommendation

The system should eventually be able to recommend a suitable academic track or specialization, for example **OEC**, based on the student's academic history.

The recommendation should not rely only on the LLM's opinion.

It should use verified academic information and student performance/history.

Where appropriate, student interests may also be considered.

The exact recommendation method is still open and should be designed after the academic data is modeled.

## 4.3 Special Cases

The system should support special student situations instead of only the standard study path.

Examples include:

- High-GPA students who want to maintain performance.
- Low-GPA students who want to improve their GPA.
- Students who want to avoid a very difficult semester.
- Students with failed or repeated courses.
- Students delayed by prerequisites.
- Students who changed department/program.
- Transfer students.
- Students trying to graduate faster.
- Students requesting a lighter workload.

Special cases must be handled using academic rules and student history, not only free-form LLM reasoning.

## 4.4 Human Advisor Handoff

When appropriate, the system should be able to create a concise summary of:

- The student's situation.
- The student's academic context.
- The important points from the conversation.
- The recommendation already produced by the system.
- Any unresolved issue requiring human review.

This summary can later be provided to the student's assigned academic advisor.

The student and advisor are expected to have accounts in the system.

## 4.5 Advisor-Side Value

After the main student-facing assets and core system are working, the project should provide some value to the academic advisor.

Possible future advisor functionality includes:

- Viewing assigned students.
- Reviewing student summaries.
- Identifying students who require attention.
- Reviewing escalated/special cases.
- Viewing academic-risk or planning signals.
- Managing advising workload more efficiently.

This should be implemented **after the core student advising system**, not before it.

## 4.6 Survey and Competitor Review

The project should include:

- Student requirements survey.
- Analysis of survey results.
- Competitor / related-system review.

The survey is already underway.

Competitor review is still required.

---

# 5. High-Level Architecture

```text
Student
   |
   v
Web Application
   |
   v
Backend
   |
   v
Local LLM
- Understand request
- Detect intent
- Extract information
- Ask for missing information
- Select approved capability
   |
   v
Conversation / Request Orchestrator
   |
   +----------------------+----------------------+----------------------+
   |                      |                      |
   v                      v                      v
Student Profile      Academic Planning         RAG
& History            Engine                    System
   |                      |                      |
   |                      |                      |
   +-----------> Verified Result <--------------+
                          |
                          v
                       Local LLM
                 - Explain result
                 - Arabic / English
                 - Present evidence
                          |
                          v
                        Student
```

The Local LLM is part of the interaction layer.

It should not independently invent academic decisions when those decisions can be computed from verified rules and student data.

---

# 6. Component Responsibilities

## 6.1 Local LLM

Responsible for:

- Natural Arabic and English conversation.
- Intent understanding.
- Information extraction from student messages.
- Asking for missing information.
- Capability/tool selection.
- Converting structured system results into natural explanations.
- Handling conversational context.
- Avoiding unsupported academic claims.

The LLM is **not the academic source of truth**.

## 6.2 Orchestrator

The orchestrator is backend control logic, not necessarily another AI agent.

It is responsible for:

- Checking required information.
- Loading student context.
- Validating requested actions.
- Calling the correct system component.
- Preventing invalid tool calls.
- Passing verified results back to the LLM.
- Managing the conversation state.

## 6.3 Student Profile and History

The student profile should eventually contain:

- Regulation.
- Program.
- Academic level.
- Completed courses.
- Course grades.
- Current courses.
- Credit hours.
- GPA where relevant.
- Failed/repeated courses.
- Track/specialization if already chosen.
- Optional preferences.

The system should support:

**Persistent Student Profile + Temporary Conversation Context**

If information is missing, the LLM can ask the student for it.

The system may offer to save newly provided information.

## 6.4 Academic Planning Engine

This is the main academic decision-support component.

Expected responsibilities:

- Course eligibility.
- Prerequisite validation.
- Co-requisite validation where applicable.
- Course dependency analysis.
- Course comparison.
- Academic progress.
- Academic-delay detection.
- Multi-semester planning.
- Workload-aware planning.
- Special-case handling.
- Future track/specialization recommendation.
- Explainable structured recommendations.

## 6.5 RAG

RAG is responsible for retrieving textual knowledge from official documents.

Examples:

- Student Affairs procedures.
- Written academic policies.
- Regulation passages.
- Add/drop rules.
- Graduation-policy text.
- Required documents.
- Written rule explanations.

RAG should return relevant evidence and metadata whenever possible.

## 6.6 Advisor-Side System

Not part of the first development slice.

Later capabilities may include:

- Assigned-student list.
- Escalated cases.
- Conversation/case summaries.
- Student academic snapshots.
- Advisor notes or actions.
- Prioritization of students requiring attention.

---

# 7. Data Architecture

The project should separate academic information into three layers.

## 7.1 Original Official Documents

Original PDFs and official documents remain the source of truth.

They must be preserved.

## 7.2 Structured Academic Data

Used for computation.

Examples:

- Course code.
- Course name.
- Credit hours.
- Prerequisites.
- Co-requisites.
- Mandatory/elective status.
- Regulation.
- Course level.
- Graduation requirements.
- Credit-hour limits.
- Course offerings when available.
- Student completed courses and grades.

## 7.3 RAG Knowledge

Used for textual retrieval and evidence.

Examples:

- Policies.
- Procedures.
- Student Affairs information.
- Written regulation text.
- Rule explanations.

## Core Rule

> **Original PDFs = Official Source of Truth**  
> **RAG = Textual Knowledge and Evidence**  
> **Structured Data = Computation and Planning**

---

# 8. Document Classification

Every collected document should be inventoried and classified as:

- **RAG**
- **STRUCTURED**
- **BOTH**

Examples:

| Document Type | Classification |
|---|---|
| Course prerequisite table | STRUCTURED |
| Student Affairs procedure PDF | RAG |
| Full academic regulation | BOTH |
| Graduation requirement table | STRUCTURED / BOTH |
| Written add/drop policy | RAG |

This classification is one of the first tasks the team should complete.

---

# 9. Structured Data Extraction

The team should not manually rewrite all PDFs into Markdown and use that as the planner's source.

The preferred process is:

```text
Official PDF
   |
   v
Automated / AI-Assisted Extraction
   |
   v
Structured Draft
   |
   v
Human Verification
   |
   v
Approved Academic Dataset
```

Critical information must be verified before it is used by the Academic Planning Engine.

Critical fields include:

- Prerequisites.
- Co-requisites.
- Credit hours.
- Mandatory/elective classification.
- Graduation rules.
- Maximum/minimum credits.
- Regulation-specific rules.
- Course availability if used for planning.

Core principle:

> **AI extracts. Humans verify. The system computes.**

---

# 10. Academic Planning Logic

The Planning Engine should distinguish between:

## 10.1 Hard Constraints

These determine whether an academic option is valid.

Examples:

- Missing prerequisite.
- Wrong regulation.
- Credit-hour limit exceeded.
- Required co-requisite missing.
- Course already completed.
- Course not available.
- Graduation rule violation.
- Academic-standing restriction.

A recommendation must never violate a hard constraint.

## 10.2 Soft Objectives / Preferences

These affect ranking among valid choices.

Examples:

- Minimize graduation delay.
- Unlock more important future courses.
- Keep the student near the standard academic path.
- Avoid overload.
- Maintain strong GPA.
- Improve a weak GPA.
- Prefer a lighter semester.
- Follow student interests.
- Progress toward a target track.

The Planning Engine may use rules, scoring, constraint solving, optimization, or a hybrid approach.

The exact implementation is not locked yet.

---

# 11. Explainable Recommendation Contract

The Planning Engine should return structured results instead of returning only plain text.

Example:

```yaml
recommended_option: Course A

reasons:
  - Unlocks Course B next semester
  - Course B is required before Course C
  - Delaying Course A may delay the dependency chain

alternatives:
  - Course D is valid but lower priority

warnings:
  - Current semester load may become heavy

consequences:
  - Taking Course A now reduces future dependency risk

relevant_rules:
  - Regulation 23 prerequisite rule

requires_human_review: false
```

The LLM then turns this into a natural student-facing answer.

---

# 12. Multi-Semester Planning

Multi-semester planning is a core project capability.

The planner should eventually support questions such as:

- "Plan my next semester."
- "Plan my next two semesters."
- "What happens if I delay this course?"
- "Can I graduate on time if I fail this course?"
- "Which summer course helps me most?"
- "How can I improve my GPA without taking a very heavy load?"

The planner should simulate valid future academic states and compare scenarios.

A first implementation does not need to solve the entire degree immediately.

Start with small planning horizons and expand gradually.

---

# 13. Track / Specialization Recommendation

This is a later core feature after student history and structured academic data are reliable.

Possible signals may include:

- Performance in relevant prerequisite/foundation courses.
- Grades in track-related subjects.
- Completed courses.
- Academic strengths.
- Student interests/preferences.
- Track requirements.
- Remaining academic path.

The output should be explainable.

Example:

```yaml
recommended_track: OEC

reasons:
  - Strong performance in relevant courses
  - Completed key prerequisites successfully
  - Academic history aligns with the track requirements

alternative_tracks:
  - Track B

confidence_or_support_level: medium
```

The system should avoid presenting track recommendation as an absolute judgment.

---

# 14. Special Cases

Special cases should be represented explicitly during requirements and testing.

Examples:

## High GPA

Goal:
- Maintain GPA.
- Avoid unnecessary overload.
- Preserve strong performance.

## Low GPA

Goal:
- Improve academic standing.
- Avoid extremely difficult load.
- Prioritize required progress safely.

## Failed / Repeated Courses

Goal:
- Re-plan dependencies.
- Avoid compounding delays.

## Changed Program / Department

Goal:
- Consider transferred/equivalent courses.
- Avoid applying the standard path blindly.

## Transfer Student

Goal:
- Account for recognized prior courses and missing requirements.

## Graduation Acceleration

Goal:
- Maximize valid progress without violating constraints.

These cases should become part of the project's evaluation scenarios.

---

# 15. Human Advisor Handoff

The system should be able to generate a concise advisor-facing case summary.

Example contents:

- Student identifier/account reference.
- Regulation.
- Current academic state.
- Student request.
- Relevant history.
- Important rules.
- System recommendation.
- Unresolved issue.
- Reason for escalation.

Example:

```text
Student requested a two-semester plan.

Key context:
- Regulation 23
- 72 completed credits
- Failed Course X once
- Course Y currently blocked by Course X

System result:
- Recommended retaking Course X next semester
- Delaying Course X risks delaying Courses Y and Z

Escalation reason:
- Student requested an exception to the normal credit-hour limit
```

This feature is later than the first vertical slice.

---

# 16. Survey Use

The student survey is not an academic rule source.

It should be used for:

- Requirements discovery.
- Feature prioritization.
- Pain-point validation.
- Real student use cases.
- Presentation/report evidence.

The team should analyze:

- Most common advising questions.
- Biggest advising pain points.
- Most requested AI features.
- Special-case frequency.
- Interest in track recommendations.
- Interest in AI + human advisor handoff.
- Differences across universities if statistically meaningful.

Survey results can influence priority, but should not override official academic rules.

---

# 17. Competitor Review

A competitor / related-system review should be completed before finalizing product positioning.

The review should compare systems on capabilities such as:

- Natural-language advising.
- Course eligibility.
- Prerequisite awareness.
- Multi-semester planning.
- Personalization.
- Student history.
- Track recommendation.
- RAG / official source grounding.
- Explainability.
- Human advisor handoff.
- Advisor-side tools.
- Privacy / local deployment.

The objective is not to copy competitors.

The objective is to identify:

- Existing solutions.
- Common missing capabilities.
- Project differentiation.
- Useful design patterns.

---

# 18. What the Team Should Start With Now

The project should **not** begin by building the full frontend or by integrating a large local LLM first.

The highest-risk dependency is the academic data and planning correctness.

The best starting point is:

## Step 1 — Academic Data Inventory

Create one inventory of all collected documents.

For every file record:

- Name.
- Regulation.
- Type.
- Contains structured academic information?
- Contains textual rules?
- RAG / STRUCTURED / BOTH.
- Verification status.
- Notes.

## Step 2 — Unified Academic Schema

Define the minimum structured model required by the first planner.

Start with:

- Course.
- Regulation.
- Prerequisite relation.
- Credit hours.
- Course type.
- Student completed courses.
- Student current courses.

Do not attempt to model every edge case on day one.

## Step 3 — Build a Small Verified Dataset

Choose a limited subset of Regulation 23 or 18.

Manually verify enough courses to support one real academic scenario.

This becomes the first development dataset.

## Step 4 — Create Golden Academic Test Cases

Before implementing the planner, write expected academic outcomes.

Example:

```text
Student:
- Regulation 23
- Completed A and B
- Has not completed C

Question:
Can the student take D?

Expected:
No

Reason:
C is a prerequisite for D
```

These test cases become the truth used to validate the engine.

## Step 5 — Implement Planning Engine v0

First capabilities only:

1. Course lookup.
2. Prerequisite validation.
3. Eligibility.
4. Basic dependency lookup.
5. Structured explanation.

Do not start with full multi-semester optimization.

## Step 6 — Build RAG v0 in Parallel

Use a small official document subset.

Goal:

- Ingest.
- Retrieve.
- Return correct text.
- Preserve source/page metadata.
- Produce citations.

Do not ingest every document first.

## Step 7 — Define the LLM Tool Contract

Before selecting/finalizing a local model, define what the LLM must be able to call.

Example conceptual tools:

```text
get_student_profile
check_course_eligibility
compare_courses
get_course_dependencies
plan_semesters
search_official_documents
save_profile_update
escalate_to_advisor
```

The exact implementation can change.

## Step 8 — Local LLM Benchmark

Test several candidate local models using the same small evaluation set.

Evaluate:

- Arabic.
- English.
- Intent understanding.
- Structured output.
- Tool selection.
- Latency.
- Hardware usage.

Do not choose the final model based only on reputation.

## Step 9 — First End-to-End Vertical Slice

The first complete demo should be intentionally small.

Example:

```text
Student:
"I am Regulation 23. Can I take Course X?"

System:
1. Understands the request.
2. Loads student context.
3. Calls eligibility logic.
4. Checks verified structured academic data.
5. Returns a structured result.
6. Retrieves an official rule if useful.
7. LLM explains the answer naturally.
```

Once this works reliably, expand.

---

# 19. Recommended Five Parallel Workstreams

The team has five members.

Do not assign names until strengths and preferences are considered.

## Workstream A — Academic Data & Rules

Responsibilities:

- Document inventory.
- Classification.
- Structured schema.
- Extraction.
- Verification.
- Rule catalog.

## Workstream B — Academic Planning Engine

Responsibilities:

- Eligibility.
- Prerequisites.
- Dependency graph.
- Rule execution.
- Structured recommendation format.
- Golden test cases.

## Workstream C — RAG & Document Pipeline

Responsibilities:

- PDF ingestion.
- Text extraction.
- Chunking/segmentation.
- Metadata.
- Retrieval.
- Citation evaluation.

## Workstream D — Local LLM & Orchestration

Responsibilities:

- Local model benchmarking.
- Intent schema.
- Tool/capability contracts.
- Missing-information flow.
- Structured outputs.
- Conversation orchestration.

## Workstream E — Product Integration & Evaluation

Responsibilities:

- Survey analysis.
- Competitor review.
- Student/advisor user flows.
- API/interface contracts.
- Evaluation dataset coordination.
- Basic web prototype after backend contracts stabilize.

These workstreams can run in parallel, but they must share the same agreed data contracts.

---

# 20. First Development Milestone

The first milestone should **not** be "complete the whole advisor."

It should be:

## Milestone 1 — Verified Advising Slice

A student can:

1. Have a minimal academic profile.
2. Ask about one course or compare two courses.
3. Have eligibility checked from verified structured data.
4. See prerequisite/dependency reasoning.
5. Receive a clear natural-language answer.
6. Receive an official citation when relevant.

### Milestone 1 Does Not Need

- Full advisor dashboard.
- Full track recommendation.
- Full multi-semester optimization.
- Every regulation document.
- Every Student Affairs question.
- Mobile application.
- Tutor.
- ML prediction.

This milestone proves the architecture before scope expands.

---

# 21. Development Order After Milestone 1

Recommended order:

```text
Academic Data Foundation
        ↓
Eligibility + Prerequisites
        ↓
Dependency Analysis
        ↓
Course Comparison
        ↓
Student Profile / History
        ↓
Multi-Semester Planning
        ↓
Special-Case Personalization
        ↓
Track Recommendation
        ↓
Human Advisor Handoff
        ↓
Advisor-Side Tools
```

RAG and Local LLM integration can develop in parallel with the academic engine.

---

# 22. Testing Strategy

Testing should exist from the beginning.

## Academic Engine

Test:

- Eligibility.
- Prerequisites.
- Credit rules.
- Dependencies.
- Special cases.
- Plan validity.

## RAG

Test:

- Retrieval relevance.
- Correct source.
- Correct page/section.
- Unsupported-answer rate.

## Local LLM

Test:

- Intent extraction.
- Structured output.
- Missing-information questions.
- Tool selection.
- Arabic/English quality.

## End-to-End

Test complete student scenarios.

The strongest evaluation set will contain real, supervisor/advisor-verified academic cases.

---

# 23. Open Decisions

The following are intentionally not locked yet.

- Exact local LLM.
- Exact backend framework.
- Exact frontend framework.
- Exact database.
- Exact vector/search system.
- Exact planning algorithm.
- Whether course dependencies are stored directly as a graph or derived.
- Exact track recommendation method.
- Advisor dashboard depth.
- Automatic document upload/update scope.
- Full on-prem deployment scope beyond the LLM.
- Exact authentication/account implementation.

These should be decided when enough evidence exists.

---

# 24. Decisions That Should Be Clarified Soon

The team should obtain or define answers for:

1. Exact official name of the supported academic program.
2. Which Regulation 18/23 documents are authoritative when documents conflict.
3. Whether course offerings by semester/summer are available.
4. Whether historical student grade data can be used.
5. Which rules affect GPA-based academic load.
6. Exact track/specialization rules and available tracks.
7. How students are assigned to academic advisors.
8. Whether advisor summaries are sent automatically or only after student approval.
9. Whether admin document upload is a required deliverable.
10. How the final system will be academically validated.

---

# 25. Scope-Control Rules

To keep the project feasible:

- Do not support all departments in the first version.
- Do not support all universities because the survey included multiple universities.
- Do not build a full tutor before the advisor.
- Do not let the LLM replace academic rules.
- Do not automate exceptional approvals.
- Do not build advisor dashboards before the student core works.
- Do not ingest every PDF before proving the pipeline on a small subset.
- Do not choose a complicated optimizer before simple planner behavior is verified.
- Do not add predictive ML unless useful historical data actually exists.

---

# 26. Core Product Principle

The central design idea of the project is:

> **The LLM communicates.  
> The Planning Engine computes.  
> Structured data enforces academic rules.  
> RAG retrieves official evidence.  
> Student history personalizes the result.  
> Human advisors handle exceptions.**

---

# 27. Immediate Team Kickoff Checklist

Before writing large amounts of code, complete the following:

- [ ] Create the document inventory.
- [ ] Classify PDFs as RAG / STRUCTURED / BOTH.
- [ ] Define the first structured academic schema.
- [ ] Select one small Regulation 18/23 subset for Milestone 1.
- [ ] Verify that subset manually.
- [ ] Write 15-30 golden academic test cases.
- [ ] Define the Planning Engine structured output contract.
- [ ] Define initial LLM tool/capability contracts.
- [ ] Build RAG v0 on a small official document set.
- [ ] Benchmark initial local LLM candidates.
- [ ] Analyze survey results.
- [ ] Start competitor review.
- [ ] Agree on first end-to-end vertical slice.
- [ ] Only then expand into full multi-semester planning and personalization.

---

# 28. Definition of the First Successful Demo

A first successful technical demo is reached when:

> A student asks a real academic question in natural language, the system understands the intent, uses the student's profile if available, calls verified academic logic, retrieves official evidence when needed, and returns a correct, explainable answer without relying on unsupported LLM reasoning.

Once this is reliable, the project is ready to expand into:

- Multi-semester planning.
- Special cases.
- Track recommendation.
- Advisor handoff.
- Advisor-side management features.

---

# 29. Current Next Step

**Start with the Academic Data Foundation and Golden Test Cases.**

This is the highest-leverage next step because every major project component depends on reliable academic information.

At the same time, the rest of the team can work in parallel on:

- Planning Engine v0.
- RAG v0.
- Local LLM/orchestration evaluation.
- Survey analysis and competitor review.

The first shared integration target is the **Verified Advising Slice** described in this document.
