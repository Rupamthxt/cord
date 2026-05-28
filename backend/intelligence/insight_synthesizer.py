import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class InsightSynthesizer:
    """
    Synthesizes aggregated operational evidence, query profiles,
    and root-cause analyses into highly structured, evidence-linked summaries.
    """

    async def synthesize(
        self,
        query: str,
        query_classification: Dict[str, Any],
        aggregated_evidence: Dict[str, Any],
        root_cause_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Builds a traceable operational insight payload.
        """
        logger.info("Synthesizing evidence and reasoning results...")
        
        chunks = aggregated_evidence.get("chunks", [])
        events = aggregated_evidence.get("events", [])
        patterns = root_cause_analysis.get("matched_patterns", [])
        query_type = query_classification["query_type"]
        
        # 1. Synthesize concise Summary statement
        summary = None
        
        # Try dynamic LLM summarization if Ollama is available
        from backend.extraction.ollama_client import ollama_client
        if await ollama_client.is_available():
            try:
                context_str = ""
                for i, c in enumerate(chunks[:3]):
                    context_str += f"\n[{i+1}] Source: {c.get('source')} | Title: {c.get('metadata', {}).get('title') or c.get('source')}\nContent: {c.get('content')}\n"
                
                events_str = ""
                for ev in events[:5]:
                    events_str += f"- {ev.get('timestamp', 'N/A').split('T')[0]} | [{ev.get('event_type')}] {ev.get('title')}: {ev.get('summary')}\n"
                
                prompt = (
                    f"You are the CORD AI Assistant, an expert SRE and operational intelligence system.\n"
                    f"Synthesize a highly simplified, direct, and concise summary of the incident's root cause, impact, and remediation.\n"
                    f"Use ONLY the retrieved system log chunks and operational events timeline below.\n"
                    f"Keep the summary extremely clear, simplified, and easy for a developer to understand at a glance.\n"
                    f"Do NOT include conversational preambles, greetings, or meta-comments. Start directly with the summary sections.\n\n"
                    f"Format the output EXACTLY as follows:\n"
                    f"**Root Cause**: (A 1-sentence explanation of what failed and why, in simple terms)\n"
                    f"**Impact**: (What systems/services were affected)\n"
                    f"**Remediation**: (How to correct the issue or what actions were taken to fix it)\n\n"
                    f"--- USER QUERY: {query} ---\n\n"
                    f"--- RETRIEVED SYSTEM LOG CHUNKS ---\n{context_str or 'No vector chunks matched.'}\n\n"
                    f"--- RETRIEVED EVENTS TIMELINE ---\n{events_str or 'No events logged.'}\n\n"
                    f"Summary:"
                )
                
                logger.info("Generating operational insight summary via Ollama...")
                summary = await ollama_client.generate(prompt=prompt, temperature=0.2)
                if summary:
                    summary = summary.strip()
            except Exception as e:
                logger.warning(f"Ollama insight synthesis failed: {e}. Falling back to programmatic reasoning.")
                summary = None

        if not summary:
            # Rule-based programmatic fallback
            if query_type == "root_cause_analysis":
                primary_trigger = "unknown"
                if root_cause_analysis.get("correlations"):
                    first_link = root_cause_analysis["correlations"][0]
                    from_id = first_link["from_event"]
                    # Find event title
                    for ev in events:
                        if ev["event_id"] == from_id:
                            primary_trigger = ev["title"]
                            break
                
                if primary_trigger != "unknown":
                    summary = (
                        f"**Root Cause**: Primary trigger identified as '{primary_trigger}'.\n"
                        f"**Impact**: Potential gateway instability and client-side timeouts.\n"
                        f"**Remediation**: Investigate '{primary_trigger}' events and check system limits."
                    )
                elif chunks:
                    top_chunk = chunks[0]
                    chunk_excerpt = top_chunk.get("content", "")
                    excerpt_len = min(800, len(chunk_excerpt))
                    clean_excerpt = " ".join(chunk_excerpt[:excerpt_len].strip().split())
                    
                    # Clean up mock database strings like "Root cause details for query '...' were identified in ...:"
                    import re
                    clean_excerpt = re.sub(
                        r"^Root\s+cause\s+details\s+for\s+query\s+'.*?'\s+were\s+identified\s+in\s+.*?:",
                        "",
                        clean_excerpt,
                        flags=re.IGNORECASE
                    ).strip()
                    
                    if clean_excerpt.startswith('"') and clean_excerpt.endswith('"'):
                        clean_excerpt = clean_excerpt[1:-1].strip()
                    
                    # Try to extract subparts if it contains them
                    rc_match = re.search(r"Root\s+Cause:\s*(.*?)(?=(?:Observed\s+Effects:|Actions\s+Taken:|$))", clean_excerpt, re.IGNORECASE)
                    eff_match = re.search(r"(?:Observed\s+Effects|Impact):\s*(.*?)(?=(?:Actions\s+Taken|Root\s+Cause:|$))", clean_excerpt, re.IGNORECASE)
                    act_match = re.search(r"(?:Actions\s+Taken|Remediation):\s*(.*?)(?=(?:Root\s+Cause:|Observed\s+Effects:|$))", clean_excerpt, re.IGNORECASE)
                    
                    rc = rc_match.group(1).strip() if rc_match else ""
                    impact = eff_match.group(1).strip() if eff_match else ""
                    remediation = act_match.group(1).strip() if act_match else ""
                    
                    if not rc:
                        rc = f"Telemetry alert matches context: {clean_excerpt[:150]}..."
                    if not impact:
                        impact = "Service latency and authentication errors."
                    if not remediation:
                        remediation = "Apply recent patch, verify connection pools, and run diagnostics."
                        
                    summary = (
                        f"**Root Cause**: {rc}\n"
                        f"**Impact**: {impact}\n"
                        f"**Remediation**: {remediation}"
                    )
                else:
                    summary = (
                        f"**Root Cause**: Primary trigger identified as 'unknown'.\n"
                        f"**Impact**: Intermittent application failures in active workspace.\n"
                        f"**Remediation**: Inspect live system execution logs and run verification queries."
                    )
            elif query_type == "recurring_issue":
                problem_entity = "unknown"
                if patterns:
                    # Find recurring incident patterns
                    recurring = [p for p in patterns if p["pattern_type"] == "recurring_incident"]
                    if recurring:
                        problem_entity = recurring[0]["name"]
                
                summary = (
                    f"**Root Cause**: Recurring bottleneck profile detected matching '{problem_entity}'.\n"
                    f"**Impact**: Repeated bottlenecks and operational performance degradation.\n"
                    f"**Remediation**: Adjust connector limits and clean up duplicate documents."
                )
            elif query_type == "trend_analysis":
                summary = (
                    f"**Root Cause**: Temporal distribution analysis of workspace events.\n"
                    f"**Impact**: Fluctuations in workspace activity ({len(events)} events registered).\n"
                    f"**Remediation**: Establish alert baselines and monitor traffic spikes."
                )
            else:
                summary = (
                    f"**Root Cause**: Diagnostic report compiled for '{query}'.\n"
                    f"**Impact**: Found {len(chunks)} chunks and {len(events)} events of interest.\n"
                    f"**Remediation**: Review the specific event timestamps and vector evidence details."
                )

        # 2. Extract key findings (traceable bullet points mapping back to sources)
        key_findings = []
        for i, c in enumerate(chunks[:3]):
            source_info = f"{c['source']}:{c['metadata'].get('path') or 'doc'}"
            key_findings.append({
                "finding": f"Semantic overlap found in {c['source_type']}: '{c['content'][:150].strip()}...'",
                "source": source_info,
                "evidence_chunk_id": c["id"]
            })
            
        for pat in patterns[:2]:
            key_findings.append({
                "finding": f"Registered alert pattern: '{pat['name']}' ({pat['description']})",
                "source": "SQLite:patterns",
                "pattern_id": pat["pattern_id"]
            })

        # 3. Escalation path chronological mapping
        escalation_path = []
        for step in root_cause_analysis.get("chain", []):
            escalation_path.append({
                "event_id": step["event_id"],
                "title": step["title"],
                "timestamp": step["timestamp"],
                "type": step["event_type"]
            })

        # 4. Recurring issues mapping
        recurring_issues = []
        for pat in patterns:
            if pat["pattern_type"] == "recurring_incident":
                recurring_issues.append({
                    "issue_name": pat["name"],
                    "description": pat["description"],
                    "severity": pat["severity"],
                    "confidence": pat["confidence"]
                })

        # 5. Combined confidence score calculation
        confidence_score = (
            (query_classification["confidence"] * 0.3) + 
            (root_cause_analysis["confidence_score"] * 0.7)
        )
        
        confidence_explanation = (
            f"Confidence score {confidence_score:.2f} derived from query parsing match "
            f"({query_classification['confidence']:.2f}) and relational database correlation traces "
            f"({root_cause_analysis['confidence_score']:.2f})."
        )

        return {
            "summary": summary,
            "key_findings": key_findings,
            "escalation_path": escalation_path,
            "recurring_issues": recurring_issues,
            "confidence_score": round(confidence_score, 2),
            "confidence_explanation": confidence_explanation
        }
