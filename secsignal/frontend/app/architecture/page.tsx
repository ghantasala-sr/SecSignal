import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Architecture — SecSignal",
  description:
    "System architecture, data lineage, and design patterns behind the SecSignal SEC filing intelligence platform.",
};

/* ------------------------------------------------------------------ */
/*  Reusable tiny components                                          */
/* ------------------------------------------------------------------ */

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="font-heading text-2xl tracking-tight mb-4">{title}</h2>
      {children}
    </section>
  );
}

function Diagram({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/30 bg-card/40 p-5 overflow-x-auto">
      <pre className="text-xs leading-relaxed text-muted-foreground font-mono whitespace-pre">
        {children}
      </pre>
    </div>
  );
}

function SubSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground/90">{title}</h3>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Table of contents links                                           */
/* ------------------------------------------------------------------ */

const TOC = [
  { id: "overview", label: "System Overview" },
  { id: "high-level", label: "High-Level Architecture" },
  { id: "low-level", label: "Low-Level Architecture" },
  { id: "data-lineage", label: "Data Lineage" },
  { id: "patterns", label: "Design Patterns" },
  { id: "tech-stack", label: "Tech Stack" },
];

/* ------------------------------------------------------------------ */
/*  Page                                                              */
/* ------------------------------------------------------------------ */

export default function ArchitecturePage() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-12 space-y-14">
        {/* Page title */}
        <div className="space-y-3">
          <h1 className="font-heading text-3xl md:text-4xl tracking-tight">
            Architecture &amp; Data Lineage
          </h1>
          <p className="text-muted-foreground text-sm max-w-2xl">
            A comprehensive overview of how SecSignal ingests SEC filings,
            processes them through Snowflake Cortex, and serves intelligent
            answers via an agentic RAG pipeline.
          </p>
          {/* TOC */}
          <nav className="flex flex-wrap gap-2 pt-2">
            {TOC.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors border border-border/30 rounded px-2.5 py-1"
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        {/* -------------------------------------------------------- */}
        {/*  1. System Overview                                      */}
        {/* -------------------------------------------------------- */}
        <Section id="overview" title="System Overview">
          <p className="text-sm text-muted-foreground leading-relaxed">
            SecSignal is an agentic RAG (Retrieval-Augmented Generation) system
            that transforms raw SEC EDGAR filings into actionable financial
            intelligence. Users ask natural-language questions about company
            trends, cross-company comparisons, or filing anomalies. A LangGraph
            supervisor classifies the query, routes it to a specialist agent,
            enriches it with real-time web data, and synthesizes a final answer
            with charts, sources, and anomaly scores &mdash; all powered by
            Snowflake Cortex AI functions.
          </p>
        </Section>

        {/* -------------------------------------------------------- */}
        {/*  2. High-Level Architecture                              */}
        {/* -------------------------------------------------------- */}
        <Section id="high-level" title="High-Level Architecture">
          <Diagram>
{`┌──────────────┐     ┌───────────────────────────────────────────────────┐
│  SEC EDGAR   │────▶│              Ingestion Layer                      │
│   (EFTS +    │     │  EdgarClient ─▶ FilingParser ─▶ Snowflake RAW    │
│ Submissions) │     └───────────────────────┬───────────────────────────┘
└──────────────┘                             │
                                             ▼
                          ┌──────────────────────────────────┐
                          │       Processing Layer           │
                          │  AI_PARSE_DOCUMENT (LAYOUT mode) │
                          │  Image extraction + Chart OCR    │
                          └──────────────┬───────────────────┘
                                         │
                    ┌────────────────────┬┴────────────────────┐
                    ▼                    ▼                     ▼
          ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
          │  dbt Pipeline   │  │ Text Embeddings │  │ Image Embeddings│
          │ staging ─▶ int  │  │ Arctic embed    │  │ Voyage multi-   │
          │ ─▶ marts        │  │ 1024d           │  │ modal-3 1024d   │
          └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
                   │                    │                     │
                   └────────────────────┼─────────────────────┘
                                        ▼
                          ┌──────────────────────────────────┐
                          │     Cortex Search Service        │
                          │     FILING_SEARCH_SERVICE        │
                          │     (semantic retrieval)         │
                          └──────────────┬───────────────────┘
                                         │
                                         ▼
┌────────────┐    ┌─────────────────────────────────────────────────────┐
│  User      │───▶│            LangGraph Agent System                  │
│  Query     │    │  classify ─▶ specialist ─▶ web_search ─▶ synthesize│
└────────────┘    └──────────────────────┬──────────────────────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────────┐
                          │   FastAPI (SSE streaming)        │
                          │   /api/query + /api/query/stream │
                          └──────────────┬───────────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────────┐
                          │   Next.js 16 Frontend            │
                          │   App Router + shadcn/ui         │
                          │   recharts + react-markdown      │
                          └──────────────────────────────────┘`}
          </Diagram>
        </Section>

        {/* -------------------------------------------------------- */}
        {/*  3. Low-Level Architecture                               */}
        {/* -------------------------------------------------------- */}
        <Section id="low-level" title="Low-Level Architecture">
          <div className="space-y-6">
            {/* Ingestion */}
            <SubSection title="Ingestion Layer">
              <p className="text-xs text-muted-foreground leading-relaxed">
                <strong className="text-foreground/80">EdgarClient</strong>{" "}
                queries the EDGAR Full-Text Search (EFTS) API and Submissions
                API with async HTTP, rate-limited to SEC guidelines. Results are
                filtered by form type (10-K, 10-Q) and date range.
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <strong className="text-foreground/80">FilingParser</strong>{" "}
                performs section-aware HTML parsing using BeautifulSoup. It
                identifies Items (1, 1A, 7, 7A, 8) via regex patterns against a{" "}
                <code className="text-primary/80">FilingSection</code> enum,
                applies TOC deduplication (keeping the longest match per item),
                and calls{" "}
                <code className="text-primary/80">chunk_text()</code> to split
                sections into overlapping chunks (1500 chars, 200 overlap) for
                embedding.
              </p>
              <Diagram>
{`EDGAR EFTS API ──▶ EdgarClient.search_filings()
                        │
                        ▼
              EdgarClient.fetch_filing_document()
                        │
                        ▼
              FilingParser.parse()
              ├── extract_sections()  [regex Item matching]
              ├── deduplicate_toc()   [keep longest per Item]
              └── chunk_text()        [1500 char chunks, 200 overlap]
                        │
                        ▼
              Snowflake RAW tables
              ├── RAW_COMPANIES
              ├── RAW_FILINGS
              └── RAW_FILING_SECTIONS`}
              </Diagram>
            </SubSection>

            {/* Processing */}
            <SubSection title="Processing Layer">
              <p className="text-xs text-muted-foreground leading-relaxed">
                <strong className="text-foreground/80">
                  AI_PARSE_DOCUMENT
                </strong>{" "}
                (LAYOUT mode) extracts structured text and embedded images from
                filing PDFs. Images are stored in{" "}
                <code className="text-primary/80">FILING_IMAGES</code> and
                analyzed via{" "}
                <code className="text-primary/80">CORTEX.AI_EXTRACT</code> to
                produce chart metadata in{" "}
                <code className="text-primary/80">CHART_EXTRACTS</code>.
              </p>
            </SubSection>

            {/* Embeddings */}
            <SubSection title="Dual Embedding Pipeline">
              <p className="text-xs text-muted-foreground leading-relaxed">
                SecSignal uses two embedding models in the same 1024-dimensional
                space:
              </p>
              <ul className="text-xs text-muted-foreground leading-relaxed list-disc list-inside space-y-1 pl-2">
                <li>
                  <strong className="text-foreground/80">
                    Arctic embed (text-to-text)
                  </strong>{" "}
                  &mdash; via{" "}
                  <code className="text-primary/80">
                    EMBED_TEXT_1024(&apos;snowflake-arctic-embed-l-v2.0&apos;)
                  </code>
                  . Populates TEXT_EMBEDDINGS and SEARCH_CORPUS for Cortex
                  Search.
                </li>
                <li>
                  <strong className="text-foreground/80">
                    Voyage multimodal-3 (cross-modal)
                  </strong>{" "}
                  &mdash; via{" "}
                  <code className="text-primary/80">
                    EMBED_TEXT_1024(&apos;voyage-multimodal-3&apos;)
                  </code>
                  . Encodes chart image descriptions into IMAGE_EMBEDDINGS for
                  cross-modal retrieval.
                </li>
              </ul>
              <Diagram>
{`Text chunks ──▶ Arctic embed (1024d) ──▶ TEXT_EMBEDDINGS
                                      └──▶ SEARCH_CORPUS (Cortex Search)

Image descriptions ──▶ Voyage multimodal-3 (1024d) ──▶ IMAGE_EMBEDDINGS`}
              </Diagram>
            </SubSection>

            {/* dbt */}
            <SubSection title="dbt Transformation Pipeline">
              <p className="text-xs text-muted-foreground leading-relaxed">
                A 12-model dbt project transforms raw data through three layers:
              </p>
              <Diagram>
{`STAGING (stg_*)                INTERMEDIATE (int_*)           MARTS (fct_*, dim_*)
─────────────                  ────────────────               ──────────────────
stg_companies          ──▶     int_parsed_sections    ──▶     fct_risk_factors
stg_filings            ──▶     int_chart_extracts     ──▶     fct_financials
stg_sections                                          ──▶     fct_chart_data
stg_filing_images                                     ──▶     dim_filing_images
stg_chart_extracts`}
              </Diagram>
            </SubSection>

            {/* Agent System */}
            <SubSection title="LangGraph Agent System">
              <p className="text-xs text-muted-foreground leading-relaxed">
                The agent system is a LangGraph{" "}
                <code className="text-primary/80">StateGraph</code> with a{" "}
                <code className="text-primary/80">FilingState</code> TypedDict.
                List fields use{" "}
                <code className="text-primary/80">
                  Annotated[list, operator.add]
                </code>{" "}
                so multiple nodes can contribute items that auto-merge.
              </p>
              <Diagram>
{`                    ┌─────────────────┐
                    │  classify_query  │
                    │  (Supervisor)    │
                    └────────┬────────┘
                             │ conditional routing
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
     ┌──────────────┐ ┌───────────┐ ┌───────────────┐
     │ trend_agent  │ │ comparison│ │ anomaly_agent │
     │              │ │ _agent    │ │               │
     └──────┬───────┘ └─────┬─────┘ └──────┬────────┘
            │               │              │
            └───────────────┼──────────────┘
                            ▼
                  ┌──────────────────┐
                  │ web_search_agent │
                  │ (Cortex Agent +  │
                  │  AGENT_RUN)      │
                  └────────┬─────────┘
                           ▼
                  ┌──────────────────┐
                  │   synthesizer    │
                  │  (Cortex        │
                  │   COMPLETE)      │
                  └──────────────────┘

  State fields (operator.add annotation):
  ├── sources: list[dict]         # filing citations
  ├── charts: list[dict]          # retrieved chart data
  ├── anomaly_scores: list[dict]  # z-score anomalies
  ├── generated_charts: list[dict]# LLM-extracted charts
  ├── web_sources: list[dict]     # web search citations
  └── trajectory: list[str]       # step-by-step trace`}
              </Diagram>
            </SubSection>

            {/* API Layer */}
            <SubSection title="API Layer">
              <p className="text-xs text-muted-foreground leading-relaxed">
                FastAPI serves two endpoints:{" "}
                <code className="text-primary/80">POST /api/query</code> for
                synchronous responses and{" "}
                <code className="text-primary/80">
                  POST /api/query/stream
                </code>{" "}
                for Server-Sent Events (SSE). The streaming endpoint uses an{" "}
                <code className="text-primary/80">asyncio.Queue</code> bridge
                &mdash;{" "}
                <code className="text-primary/80">run_query_stream()</code>{" "}
                yields trajectory steps and the final result into the queue,
                while FastAPI&apos;s{" "}
                <code className="text-primary/80">StreamingResponse</code>{" "}
                drains it to the client.
              </p>
            </SubSection>

            {/* Frontend */}
            <SubSection title="Frontend">
              <p className="text-xs text-muted-foreground leading-relaxed">
                Next.js 16 App Router with a single-page chat interface. The{" "}
                <code className="text-primary/80">useQueryStream</code> hook
                connects to the SSE endpoint via{" "}
                <code className="text-primary/80">EventSource</code>, parsing
                trajectory and result events into React state. Charts are
                rendered with recharts (BarChart, LineChart,
                ResponsiveContainer), and markdown answers use react-markdown
                with remark-gfm for pipe table support. The UI is styled with
                shadcn/ui + Tailwind 4 using oklch colors (warm off-black
                background, muted teal primary).
              </p>
            </SubSection>

            {/* Airflow */}
            <SubSection title="Airflow Orchestration">
              <p className="text-xs text-muted-foreground leading-relaxed">
                A weekly Airflow DAG orchestrates the end-to-end pipeline:
              </p>
              <Diagram>
{`fetch_metadata ──▶ process_filings ──┬──▶ process_images ──▶ embed_images
                                     │
                                     └──▶ run_dbt ──────────▶ embed_text

Schedule: Weekly (Sunday 2:00 AM UTC)
Fan-out: process_filings triggers both image and dbt branches in parallel
Fan-in: embed_images and embed_text run after their respective upstream tasks`}
              </Diagram>
            </SubSection>
          </div>
        </Section>

        {/* -------------------------------------------------------- */}
        {/*  4. Data Lineage                                         */}
        {/* -------------------------------------------------------- */}
        <Section id="data-lineage" title="Data Lineage">
          <p className="text-sm text-muted-foreground leading-relaxed mb-4">
            End-to-end data flow from SEC EDGAR to the user&apos;s browser:
          </p>

          <SubSection title="Filing Ingestion Lineage">
            <Diagram>
{`SEC EDGAR (EFTS API)
    │
    ▼
RAW_COMPANIES ◄── company metadata (CIK, name, ticker, SIC)
RAW_FILINGS ◄──── filing metadata (accession, form type, date)
RAW_FILING_SECTIONS ◄── parsed section text (Item 1, 1A, 7, 7A, 8)
    │
    ▼  (dbt staging)
stg_companies, stg_filings, stg_sections
    │
    ▼  (dbt intermediate)
int_parsed_sections ◄── joined filings + sections + companies
int_chart_extracts  ◄── enriched chart data with filing context
    │
    ▼  (dbt marts)
fct_risk_factors   ◄── risk factor text by company/filing/period
fct_financials     ◄── extracted financial metrics (revenue, net income, etc.)
fct_chart_data     ◄── chart data points with filing attribution
dim_filing_images  ◄── image metadata dimension table`}
            </Diagram>
          </SubSection>

          <SubSection title="Image Pipeline Lineage">
            <Diagram>
{`RAW_FILINGS
    │
    ▼  AI_PARSE_DOCUMENT (LAYOUT mode)
FILING_IMAGES ◄── extracted images with page location
    │
    ▼  AI_EXTRACT (chart analysis)
CHART_EXTRACTS ◄── chart type, title, data points, description
    │
    ▼  Voyage multimodal-3
IMAGE_EMBEDDINGS ◄── 1024d cross-modal vectors`}
            </Diagram>
          </SubSection>

          <SubSection title="Text Embedding Lineage">
            <Diagram>
{`INT_PARSED_SECTIONS
    │
    ▼  chunk_text() [1500 chars, 200 overlap]
Text chunks
    │
    ▼  Arctic embed (snowflake-arctic-embed-l-v2.0)
TEXT_EMBEDDINGS ◄── 1024d text vectors
    │
    ▼  Cortex Search indexing
SEARCH_CORPUS ──▶ FILING_SEARCH_SERVICE (semantic retrieval)`}
            </Diagram>
          </SubSection>

          <SubSection title="Query-Time Data Flow">
            <Diagram>
{`User question
    │
    ▼  classify_query (CORTEX.COMPLETE)
Query type + tickers extracted
    │
    ├──▶ Specialist Agent
    │    ├── CORTEX.SEARCH_PREVIEW() ──▶ FILING_SEARCH_SERVICE ──▶ sources
    │    ├── SQL queries ──▶ fct_financials, fct_risk_factors ──▶ charts
    │    └── SQL queries ──▶ EXTRACTED_FINANCIALS ──▶ anomaly z-scores
    │
    ├──▶ Web Search Agent
    │    ├── CORTEX.AGENT_RUN() ──▶ SECSIGNAL_WEB_AGENT ──▶ web_context
    │    └── CORTEX.COMPLETE() ──▶ chart data extraction ──▶ generated_charts
    │
    ▼  synthesizer (CORTEX.COMPLETE)
Final answer (markdown + charts + sources + anomalies)
    │
    ▼  FastAPI SSE stream
    │
    ▼  Next.js EventSource
Browser (react-markdown + recharts)`}
            </Diagram>
          </SubSection>
        </Section>

        {/* -------------------------------------------------------- */}
        {/*  5. Design Patterns                                      */}
        {/* -------------------------------------------------------- */}
        <Section id="patterns" title="Design Patterns">
          <div className="space-y-5">
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                1. Agentic RAG (Supervisor &rarr; Specialist &rarr; Synthesizer)
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Rather than a monolithic RAG pipeline, SecSignal uses a
                multi-agent architecture. A supervisor node classifies the query
                type, then conditionally routes to a specialist agent (trend,
                comparison, or anomaly). Each specialist retrieves different data
                and produces structured artifacts. A final synthesizer merges
                everything into a coherent answer. This separation of concerns
                allows each agent to be optimized independently.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                2. State Accumulation via operator.add
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                LangGraph&apos;s{" "}
                <code className="text-primary/80">
                  Annotated[list, operator.add]
                </code>{" "}
                annotation on state fields (sources, charts, trajectory, etc.)
                enables multiple nodes to append items without overwriting each
                other. When a specialist adds 3 sources and the web agent adds 2
                more, the synthesizer sees all 5 automatically.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                3. Dual Embedding Strategy
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Text-to-text retrieval uses Arctic embed for precise semantic
                search over filing sections. Cross-modal retrieval uses Voyage
                multimodal-3 to match text queries against chart image
                descriptions. Both produce 1024-dimensional vectors, enabling
                unified similarity searches across modalities.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                4. SSE Bridge Pattern (asyncio.Queue)
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                The LangGraph stream generator yields trajectory steps
                synchronously. An{" "}
                <code className="text-primary/80">asyncio.Queue</code> bridges
                this into FastAPI&apos;s async world &mdash; a background thread
                runs the generator and enqueues events, while the SSE response
                handler dequeues them. This prevents blocking the event loop
                during long Cortex LLM calls.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                5. TTL Dictionary Cache
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Web search and chart extraction results are cached in
                module-level dictionaries with a 5-minute TTL. Cache keys
                combine the normalized query and sorted ticker list. This avoids
                redundant Cortex AGENT_RUN and COMPLETE calls for repeated or
                similar queries within a short window.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                6. Section-Aware Parsing with TOC Deduplication
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                SEC filings often have a Table of Contents that duplicates
                section headers. The parser uses regex to match Item headings,
                then deduplicates by keeping only the longest text match per
                Item. This ensures embedding and search indices contain the full
                section content rather than TOC stubs.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                7. Conditional Routing via LangGraph Edges
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                <code className="text-primary/80">add_conditional_edges</code>{" "}
                dispatches to the correct specialist based on the classified
                query type. The routing function returns a node name string,
                keeping the graph definition declarative and the routing logic
                testable in isolation.
              </p>
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground/90">
                8. Fan-Out / Fan-In Orchestration (Airflow)
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                The weekly DAG fans out after filing processing: one branch
                extracts and embeds images, the other runs dbt transforms and
                embeds text. Both branches converge implicitly at DAG completion.
                This parallelizes the two heaviest operations (image processing
                and dbt) for faster pipeline throughput.
              </p>
            </div>
          </div>
        </Section>

        {/* -------------------------------------------------------- */}
        {/*  6. Tech Stack                                           */}
        {/* -------------------------------------------------------- */}
        <Section id="tech-stack" title="Tech Stack">
          <div className="rounded-lg border border-border/30 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border/30 bg-card/40">
                  <th className="text-left px-4 py-2.5 font-medium text-foreground/80">
                    Layer
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-foreground/80">
                    Technology
                  </th>
                  <th className="text-left px-4 py-2.5 font-medium text-foreground/80">
                    Purpose
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {[
                  ["Data Warehouse", "Snowflake", "Storage, compute, Cortex AI functions"],
                  ["LLM", "Snowflake Cortex COMPLETE", "Classification, synthesis, chart extraction"],
                  ["Search", "Cortex Search (SEARCH_PREVIEW)", "Semantic retrieval over filing sections"],
                  ["Web Search", "Cortex Agent (AGENT_RUN)", "Real-time market data and news"],
                  ["Embeddings", "Arctic embed + Voyage multimodal-3", "Text and cross-modal embeddings (1024d)"],
                  ["Doc Parsing", "Cortex AI_PARSE_DOCUMENT", "PDF layout extraction with images"],
                  ["Agent Framework", "LangGraph (StateGraph)", "Multi-agent orchestration with shared state"],
                  ["Transforms", "dbt", "SQL-based data transformation pipeline"],
                  ["Orchestration", "Apache Airflow", "Weekly DAG scheduling and monitoring"],
                  ["API", "FastAPI", "REST + SSE streaming endpoints"],
                  ["Frontend", "Next.js 16 (App Router)", "React-based UI with server components"],
                  ["UI Components", "shadcn/ui + Tailwind 4", "Component library with oklch color system"],
                  ["Charts", "recharts", "BarChart, LineChart, ResponsiveContainer"],
                  ["Markdown", "react-markdown + remark-gfm", "Answer rendering with GFM table support"],
                ].map(([layer, tech, purpose]) => (
                  <tr key={layer}>
                    <td className="px-4 py-2 text-muted-foreground">{layer}</td>
                    <td className="px-4 py-2 font-medium text-foreground/80">{tech}</td>
                    <td className="px-4 py-2 text-muted-foreground">{purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* Footer spacer */}
        <div className="pt-8 border-t border-border/30">
          <p className="text-[11px] text-muted-foreground/50 text-center">
            Powered by Snowflake Cortex &middot; Agentic RAG
          </p>
        </div>
      </div>
    </div>
  );
}
