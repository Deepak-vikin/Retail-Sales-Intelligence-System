# AI-Powered Retail Sales Intelligence Platform Using Fine-Tuned Small Language Models and Retrieval-Augmented Generation (RAG)

> **Manuscript status:** Project paper draft. Replace bracketed TODOs and pending evaluation fields with verified project and experiment information before submission. This draft distinguishes the currently described implementation from planned work; it does not report model performance or experimental outcomes that have not been measured.

**Author(s):** Deepak Vaidhyanathan,R. Kirthiga  
**Affiliation(s):** Sri Shakthi Institute Of Engineering and Technology  
**Corresponding author:** Deepak Vaidhyanathan, deepak5519u@gmail.com
**Version/date:** 1.1/10.11.2026

## Abstract

Retail operators need timely access to operational data, but answering business questions can require both structured numerical analysis and interpretation of unstructured documents. This paper describes the design and implementation status of a single-store retail sales intelligence platform that combines natural-language question answering with PostgreSQL analytics and Retrieval-Augmented Generation (RAG). The system is organized around a PostgreSQL/Supabase data model containing products, inventory, suppliers, purchases, bills, and bill items, with a FastAPI backend. Its intended hybrid routing sends questions requiring exact numerical calculations to a Text-to-SQL path and explanatory or document-oriented questions to a RAG path; questions needing both sources may combine SQL results and retrieved passages before generating a grounded response. Barcode-based billing is part of the planned or integrated product direction, but its final implementation status should be confirmed. The project has reported a development dataset containing 72,183 bills, 205,212 bill items, 73 products, 12 suppliers, 1,232 purchases, 9 categories, and 73 inventory records, spanning 2026-01-15 through 2026-11-11. These are dataset characteristics, not evidence of model accuracy or system performance. Small language model fine-tuning, robust live data ingestion, and concurrency and load testing remain planned work. Evaluation metrics and results are pending. The paper documents the system design, current status, evaluation plan, limitations, and steps required for a reproducible assessment.

**Keywords:** retail analytics; natural language interfaces; Text-to-SQL; Retrieval-Augmented Generation; small language models; PostgreSQL; FastAPI

## 1. Introduction

Retail operations produce structured records such as sales bills, line items, stock levels, supplier purchases, and product details. Managers may need to ask questions about totals, trends, inventory, or purchasing in everyday language. Other questions require explanatory context from policies, product documents, or operational guidance. A system that handles only structured queries cannot directly ground its answers in documents, while a document retrieval system alone is not designed to calculate exact totals over transactional records.

This project addresses these complementary needs through a single-store retail analytics platform. It combines a relational database query path with a document retrieval and generation path and exposes the service through a FastAPI backend. The system is designed to route questions according to the type of evidence required and, where appropriate, combine database results with retrieved material.

The project also includes a barcode-based billing direction intended to connect point-of-sale activity with the analytics data. Small language model (SLM) fine-tuning has been identified as future work. Accordingly, this paper describes a planned model-assisted capability rather than claiming that a fine-tuned model has already been trained or evaluated.

## 2. Problem Statement

Single-store retailers may have operational data distributed across transactional tables and explanatory documents. Extracting reliable answers can require database knowledge, manual calculations, and document search. The project seeks to provide a natural-language interface that selects a suitable evidence source while preserving the distinction between exact structured-data calculations and document-grounded explanations.

The central research and engineering question is: **How can a retail analytics platform route natural-language questions between relational querying and document retrieval, and combine their evidence when a question requires both, while keeping answer quality and operational reliability measurable?** The current project status does not yet establish the accuracy, latency, reliability, or user impact of the proposed approach.

## 3. Objectives

The project objectives are:

1. Maintain a relational representation of core single-store retail entities, including products, inventory, suppliers, purchases, bills, and bill items.
2. Provide a FastAPI service layer for retail analytics and natural-language interaction.
3. Route exact numerical questions to a Text-to-SQL and PostgreSQL execution path.
4. Route explanatory and document-oriented questions to a RAG retrieval and answer-generation path.
5. Support a hybrid path for questions that need both transactional evidence and document context.
6. Incorporate barcode-based billing into the retail workflow, subject to confirmation of the completed integration scope.
7. Evaluate the system with a reproducible question set and report measured results only after testing.
8. Investigate SLM fine-tuning for query generation and grounded answer generation as planned future work.

## 4. Related Work

> **TODO: Complete this section with verified scholarly and technical sources.**

Relevant work should cover natural-language interfaces to databases and Text-to-SQL; retrieval-augmented language generation; hybrid structured and unstructured question answering; small language model adaptation and fine-tuning; and retail decision-support systems. Compare prior systems by data assumptions, query execution safeguards, grounding strategy, evaluation methods, and deployment constraints. No specific prior-study findings are asserted in this placeholder section.

## 5. System Architecture

### 5.1 Overview

The proposed system has the following logical components:

1. **Retail data layer:** PostgreSQL managed through or alongside Supabase, with transactional and reference tables.
2. **Application service:** A FastAPI backend that receives requests and coordinates routing, database access, retrieval, and answer construction.
3. **Question router:** Classifies or directs a question toward structured analytics, document retrieval, or a hybrid workflow. The routing policy and its implementation details should be documented from the codebase before publication.
4. **Text-to-SQL path:** Converts a supported natural-language question into a constrained SQL query, executes it against PostgreSQL, and returns structured results for answer presentation.
5. **RAG path:** Retrieves relevant indexed documents and supplies the selected passages as context for an answer. The corpus, embedding model, vector store, chunking strategy, and retrieval configuration require project-specific documentation.
6. **Response construction:** Produces an answer grounded in the SQL result, retrieved passages, or both. The generation model and safeguards should be specified after implementation is verified.
7. **Billing workflow:** Barcode-based product identification and billing are part of the product direction. The precise deployed/integrated state is not established by the available project context.

### 5.2 Request Flows

For an exact numerical question, the intended flow is:

`Natural-language question → route to Text-to-SQL → validate query → execute against PostgreSQL → present result with appropriate context`

For a document or explanatory question, the intended flow is:

`Natural-language question → retrieve relevant passages → generate a response grounded in retrieved context`

For a question requiring both transactional values and explanation, the intended flow is:

`Natural-language question → obtain SQL result and retrieved context → combine evidence → generate a response that distinguishes the sources`

These flows describe the system design. Actual implemented controls, including query validation, read-only enforcement, authorization, citation presentation, and failure handling, must be verified and documented before claiming them as implemented.

## 6. Methodology

### 6.1 Data and Scope

The system targets single-store retail analytics. The reported development/test dataset has the following characteristics:

| Entity or property | Reported value |
|---|---:|
| Bills | 72,183 |
| Bill items | 205,212 |
| Products | 73 |
| Suppliers | 12 |
| Purchases | 1,232 |
| Categories | 9 |
| Inventory records | 73 |
| Date range | 2026-01-15 to 2026-11-11 |

These counts are project-reported dataset facts from earlier tests. Before publication, verify them against the database snapshot used for evaluation, define whether the date range refers to bill dates or all records, and report the extraction date and counting queries. The counts do not establish representativeness, data quality, or system effectiveness.

### 6.2 Natural-Language Question Processing

Questions are intended to be assigned to one of three evidence requirements: (a) exact structured analytics, (b) document-based explanation, or (c) a combination of structured and document evidence. The routing mechanism may use explicit rules, a classifier, an SLM, or a combination; the final paper should state the implemented method and version. Ambiguous questions should be handled through clarification or a safe fallback, with the actual policy reported after verification.

### 6.3 Structured Query Path

The Text-to-SQL component is intended to map supported questions to queries over the retail schema. A complete implementation description should identify the model or method, schema context supplied to generation, SQL validation and execution restrictions, treatment of nulls and dates, and handling of invalid or unsafe queries. The database remains the source of truth for exact calculations. No SQL-generation accuracy or execution success rate is available in the project information provided for this draft.

### 6.4 Retrieval-Augmented Generation Path

The RAG component is intended for explanatory or document-oriented questions. A reproducible account must specify the document collection, preprocessing, chunking, embedding model, vector index, retrieval depth, ranking method, prompt construction, and model used for answer generation. These details and retrieval or answer-quality measurements are currently pending.

### 6.5 Hybrid SQL and RAG Path

Some questions require both numerical evidence and explanatory context. The planned hybrid path obtains structured values from PostgreSQL and relevant passages from the document collection, then combines them for answer generation. The implementation should preserve provenance so that a reader can distinguish a computed value from a statement supported by retrieved text. Whether this flow is currently implemented and how evidence is attributed should be confirmed before final submission.

## 7. Database and Schema

The reported PostgreSQL/Supabase schema includes the following core entities:

| Table | Intended role |
|---|---|
| `products` | Product identifiers and descriptive or category attributes; barcode field/details to be confirmed |
| `inventory` | Stock records associated with products |
| `suppliers` | Supplier reference information |
| `purchases` | Purchase or replenishment records associated with suppliers |
| `bills` | Retail transaction headers |
| `bill_items` | Product-level line items associated with bills |

The exact columns, primary and foreign keys, constraints, indexes, money and quantity types, and deletion/update behavior are **TODO: extract from the current schema or migration files**. The table names above describe the known entities and do not imply a particular column design. For publication, include an ER diagram or schema listing and explain how transaction consistency and inventory updates are handled.

## 8. Implementation Status

Based on the available project context, the status is summarized below. Status labels should be checked against the repository and running application before final submission.

| Capability | Status supported by available information |
|---|---|
| Single-store retail analytics scope | Established project scope |
| PostgreSQL/Supabase retail schema | Schema described as present; exact implementation details require code/schema review |
| FastAPI backend | Identified as the backend; endpoints and deployed state are not documented here |
| Text-to-SQL for exact numerical analytics | Intended/implemented direction; exact completion and safeguards require verification |
| RAG for explanatory/document questions | Intended/implemented direction; corpus and retrieval configuration require verification |
| Hybrid SQL + RAG answers | Potential/planned capability; completion status requires verification |
| Barcode-based billing | Planned/integrated direction; completion status and scope require verification |
| SLM fine-tuning | Planned; not completed according to the available project facts |
| Robust live ingestion | Planned future work |
| Concurrency and load testing | Planned future work |

This project status is not a deployment claim. Hosting, production usage, availability, and security controls have not been established by the information available for this draft.

## 9. Evaluation Plan and Results

### 9.1 Evaluation Plan

Evaluation should use a documented test set of representative questions with expected answers and evidence sources. The set should include exact numerical questions, document questions, hybrid questions, ambiguous questions, and invalid or unsafe query attempts. Split question development and final assessment data where applicable, and record database snapshots, model versions, prompts, retrieval settings, and execution environment.

Recommended measures include:

- **Routing:** class-wise precision, recall, and F1 for SQL, RAG, and hybrid routing; confusion matrix; unsupported-question fallback rate.
- **Text-to-SQL:** exact-match or normalized query comparison where meaningful, execution accuracy against reference results, and invalid/unsafe query rate.
- **RAG retrieval:** Recall@k or another justified retrieval metric on a labeled relevance set.
- **Answer quality:** factual correctness, evidence support, completeness, and appropriate abstention, judged with a documented rubric and preferably more than one evaluator.
- **Hybrid answers:** correctness of computed values, support of explanatory claims, and evidence attribution.
- **System behavior:** end-to-end latency distributions, error rates, and resource use under a defined test setup.
- **Operational robustness:** concurrency and load behavior, ingestion freshness, and recovery from database, model, or retrieval failures.

Metrics must be chosen to fit the final implementation and reported with sample sizes, evaluation procedures, and uncertainty where feasible. No result should be inferred from dataset size alone.

### 9.2 Results

**Evaluation results: pending.** No verified model accuracy, routing score, retrieval score, answer-quality score, latency, throughput, load-test result, or deployment measurement was provided for this draft. Populate this section only after running and recording the evaluation described above.

| Metric | Result | Test set / conditions |
|---|---|---|
| Routing performance | [PENDING] | [TODO] |
| Text-to-SQL execution accuracy | [PENDING] | [TODO] |
| RAG retrieval quality | [PENDING] | [TODO] |
| Grounded answer quality | [PENDING] | [TODO] |
| Hybrid answer quality | [PENDING] | [TODO] |
| End-to-end latency | [PENDING] | [TODO] |
| Concurrency/load behavior | [PENDING] | [TODO] |

## 10. Limitations

The described dataset is limited to one store and may not represent other retail formats, product mixes, or operating conditions. The reported counts and date range require verification against a fixed evaluation snapshot. The available information does not specify the document corpus, models, retrieval configuration, query safeguards, or evaluation set. Fine-tuning has not been completed, so no benefit from fine-tuning can be claimed. Robust live ingestion and concurrency/load testing remain planned, limiting conclusions about freshness and scalability. Barcode-based billing and hybrid SQL-plus-RAG completion status also require confirmation. Accordingly, this draft documents a system direction and implementation status rather than a validated comparative study.

## 11. Future Work

Future work should:

1. Verify the implementation and document the exact API, schema, routing policy, retrieval pipeline, and safety controls.
2. Complete SLM fine-tuning only after preparing and validating task-specific training and held-out evaluation datasets; report model, training configuration, and results transparently.
3. Implement or strengthen live ingestion and test data freshness, idempotency, and recovery behavior.
4. Complete end-to-end barcode billing integration and verify how transactions update bills, bill items, and inventory.
5. Implement and evaluate hybrid SQL-plus-RAG responses with clear evidence provenance.
6. Conduct concurrency and load testing with disclosed hardware, software, workload, and measurement methods.
7. Evaluate on additional stores or carefully designed external datasets before making broader generalization claims.

## 12. Conclusion

This paper presents the design and current status of a single-store retail sales intelligence platform that combines relational analytics with document retrieval through a FastAPI-based service and a PostgreSQL/Supabase schema. Its central design principle is to use Text-to-SQL for exact numerical analytics, RAG for explanatory or document-based questions, and a potential hybrid path when both evidence types are needed. Project-reported data counts characterize the development dataset but do not constitute performance results. SLM fine-tuning, robust live ingestion, and concurrency/load testing remain future work. A reproducible evaluation is required before claims about accuracy, speed, reliability, or practical effectiveness can be made.

## References

> **TODO: Add verified references in the citation style required by the target venue.** Confirm bibliographic details directly from the source publications or official documentation. Cite related-work claims, the selected Text-to-SQL/RAG methods, model and embedding systems, and any evaluation methodology used. No references are fabricated in this draft.

## Information Needed to Finalize

- Author names, affiliations, corresponding-author details, target venue, and required citation style.
- Repository-backed confirmation of which endpoints, routing paths, barcode workflow, and hybrid-answer workflow are implemented.
- Exact schema definition, constraints, and diagram; API and software version details.
- Document corpus and RAG configuration, including embeddings, vector store, chunking, retrieval, and generation model.
- Text-to-SQL approach and implemented validation, authorization, and execution safeguards.
- Verified dataset snapshot, count queries, and meaning of the reported date range.
- SLM fine-tuning status and, once completed, training setup and measured results.
- Evaluation dataset, protocol, results, and test environment; no results should be inserted before measurement.
- Verified scholarly/technical references and target publication requirements.
