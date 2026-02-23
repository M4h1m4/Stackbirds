import { useState, useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import {
  getProcessingList,
  getExtraction,
  getMatching,
  getClarification,
  submitClarification,
  getCompletion,
} from '../api';
import PhaseProgressBar from '../components/PhaseProgressBar';
import styles from './ProcessingDetail.module.css';

function isStateObject(s) {
  return s && typeof s === 'object' && s.state_id && s.state_name;
}

/** decision_result from API can be a string or object like { status: "APPROVED", reasoning: "..." } */
function formatDecisionResult(decisionResult) {
  if (decisionResult == null) return '—';
  if (typeof decisionResult === 'string') return decisionResult;
  if (typeof decisionResult === 'object' && decisionResult !== null && decisionResult.status != null) {
    return String(decisionResult.status);
  }
  return '—';
}

function safeStringify(val) {
  try {
    return JSON.stringify(val, null, 2);
  } catch {
    return String(val);
  }
}

export default function ProcessingDetail() {
  const { processingId } = useParams();
  const [searchParams] = useSearchParams();
  const inboxEmail = searchParams.get('inbox_email') || '';
  const customerId = searchParams.get('customer_id') || '';
  const listEmail = inboxEmail || customerId;
  const byInbox = !!inboxEmail;
  const [processing, setProcessing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [extraction, setExtraction] = useState(null);
  const [matching, setMatching] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [completion, setCompletion] = useState(null);
  const [clarifySubmitting, setClarifySubmitting] = useState(false);
  const [clarifyAnswers, setClarifyAnswers] = useState({});

  // Find processing from list
  useEffect(() => {
    if (!listEmail || !processingId) {
      setLoading(false);
      setError('Missing inbox email / customer id or processing id');
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getProcessingList(listEmail, { byInbox })
      .then((list) => {
        if (cancelled) return;
        const proc = (Array.isArray(list) ? list : []).find((p) => p.processing_id === processingId);
        if (proc) setProcessing(proc);
        else setError('Processing not found');
      })
      .catch((err) => {
        if (!cancelled) setError(err.body?.detail || err.message || 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [listEmail, byInbox, processingId]);

  const states = processing?.states || [];
  const extractionState = states.find((s) => isStateObject(s) && s.state_name === 'Extraction');
  const matchingState = states.find((s) => isStateObject(s) && s.state_name === 'Matching');
  const clarificationStates = states.filter((s) => isStateObject(s) && s.state_name === 'Clarification');
  const currentClarificationId = clarificationStates.length > 0 ? clarificationStates[clarificationStates.length - 1].state_id : null;

  // Load extraction when we have extraction state
  useEffect(() => {
    if (!extractionState?.state_id) return;
    getExtraction(extractionState.state_id)
      .then(setExtraction)
      .catch(() => setExtraction(null));
  }, [extractionState?.state_id]);

  // Load matching when we have matching state
  useEffect(() => {
    if (!matchingState?.state_id) return;
    getMatching(matchingState.state_id)
      .then(setMatching)
      .catch(() => setMatching(null));
  }, [matchingState?.state_id]);

  // Load clarification when we have a clarification state
  useEffect(() => {
    if (!currentClarificationId) return;
    getClarification(currentClarificationId)
      .then((c) => {
        setClarification(c);
        if (c?.questions && Array.isArray(c.questions)) {
          const initial = {};
          c.questions.forEach((q, i) => {
            const id = (q && q.id) || `q${i}`;
            initial[id] = '';
          });
          setClarifyAnswers(initial);
        }
      })
      .catch(() => setClarification(null));
  }, [currentClarificationId]);

  // Load completion when phase is Completion
  useEffect(() => {
    if (processing?.user_visible_phase !== 'Completion' || !processingId) return;
    getCompletion(processingId)
      .then(setCompletion)
      .catch(() => setCompletion(null));
  }, [processing?.user_visible_phase, processingId]);

  const handleClarifySubmit = (e) => {
    e.preventDefault();
    if (!currentClarificationId || clarification?.completed) return;
    setClarifySubmitting(true);
    const questions = clarification?.questions || [];
    const answers = questions.map((q, i) => {
      const id = (q && q.id) || `q${i}`;
      const text = typeof q === 'string' ? q : (q?.text ?? '');
      return { question_id: id, value: clarifyAnswers[id] ?? '' };
    });
    submitClarification(currentClarificationId, {
      questions: clarification.questions,
      answers,
      completed: true,
    })
      .then(() => {
        setClarification((prev) => (prev ? { ...prev, completed: true, answers } : null));
        setClarifySubmitting(false);
        window.location.reload();
      })
      .catch((err) => {
        setError(err.body?.detail || err.message || 'Submit failed');
        setClarifySubmitting(false);
      });
  };

  if (loading && !processing) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>Loading…</div>
      </div>
    );
  }
  if (error && !processing) {
    return (
      <div className={styles.page}>
        <div className={styles.error} role="alert">{error}</div>
        <Link to={listEmail ? (inboxEmail ? `/processing?inbox_email=${encodeURIComponent(listEmail)}` : `/processing?customer_id=${encodeURIComponent(listEmail)}`) : '/processing'} className={styles.back}>← Back to list</Link>
      </div>
    );
  }

  const phase = processing?.user_visible_phase || 'Extraction';

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link to={listEmail ? (inboxEmail ? `/processing?inbox_email=${encodeURIComponent(listEmail)}` : `/processing?customer_id=${encodeURIComponent(listEmail)}`) : '/processing'} className={styles.back}>← Back to list</Link>
        <h1 className={styles.title}>Processing: {processing?.invoice_id}</h1>
        <PhaseProgressBar currentPhase={phase} />
      </header>

      {extractionState && (
        <section className={styles.section}>
          <h2>Extraction</h2>
          {extraction ? (
            <>
              <p><strong>Vendor:</strong> {extraction.vendor_name}</p>
              <p><strong>Total:</strong> {extraction.total_invoice_price} (tax: {extraction.tax}, shipping: {extraction.shipping})</p>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Qty</th>
                    <th>Unit price</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(extraction.items || []).map((item) => (
                    <tr key={item.item_id}>
                      <td>{item.item_name}</td>
                      <td>{item.number_of_items}</td>
                      <td>{item.unit_price}</td>
                      <td>{item.total_price_of_item}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className={styles.muted}>Loading extraction…</p>
          )}
        </section>
      )}

      {matchingState && (
        <section className={styles.section}>
          <h2>Matching</h2>
          {matching ? (
            <>
              <p><strong>Vendor:</strong> {matching.vendor}</p>
              <p>Mapping: {Object.keys(matching.mapping || {}).length} item(s) mapped to contracted rates.</p>
            </>
          ) : (
            <p className={styles.muted}>Loading matching…</p>
          )}
        </section>
      )}

      {currentClarificationId && (
        <section className={styles.section}>
          <h2>Clarification</h2>
          {clarification ? (
            clarification.completed ? (
              <p className={styles.muted}>Answered. Pipeline resuming…</p>
            ) : (
              <form onSubmit={handleClarifySubmit}>
                <ul className={styles.questionList}>
                  {(clarification.questions || []).map((q, i) => {
                    const id = (q && q.id) || `q${i}`;
                    const text = typeof q === 'string' ? q : (q?.text ?? '');
                    return (
                      <li key={id} className={styles.questionItem}>
                        <label>
                          <span className={styles.questionText}>{text}</span>
                          <input
                            type="text"
                            value={clarifyAnswers[id] ?? ''}
                            onChange={(e) => setClarifyAnswers((prev) => ({ ...prev, [id]: e.target.value }))}
                            className={styles.input}
                          />
                        </label>
                      </li>
                    );
                  })}
                </ul>
                <button type="submit" className={styles.button} disabled={clarifySubmitting}>
                  {clarifySubmitting ? 'Submitting…' : 'Submit answers'}
                </button>
              </form>
            )
          ) : (
            <p className={styles.muted}>Loading clarification…</p>
          )}
        </section>
      )}

      {phase === 'Completion' && (
        <section className={styles.section}>
          <h2>Completion</h2>
          {completion ? (
            <>
              <div className={styles.decisionWrap}>
                <span className={styles.decisionLabel}>Result</span>
                <span className={`${styles.decisionBadge} ${formatDecisionResult(completion.decision_result) === 'APPROVED' ? styles.decisionBadgeApproved : formatDecisionResult(completion.decision_result) === 'FLAGGED' ? styles.decisionBadgeFlagged : styles.decisionBadgeNeutral}`}>
                  {formatDecisionResult(completion.decision_result)}
                </span>
                {completion.decision_result && typeof completion.decision_result === 'object' && completion.decision_result.vendor_match_confidence != null && (
                  <span className={styles.confidence}>
                    Vendor match confidence: <strong>{Math.round(Number(completion.decision_result.vendor_match_confidence) * 100)}%</strong>
                  </span>
                )}
              </div>
              {completion.decision_result && typeof completion.decision_result === 'object' && completion.decision_result.reasoning && (
                <p className={styles.reasoning}>{completion.decision_result.reasoning}</p>
              )}
              {completion.reconciliation_report != null && (
                <div className={styles.report}>
                  <h3>Reconciliation report</h3>
                  {typeof completion.reconciliation_report === 'string' ? (
                    <pre className={styles.reportText}>{completion.reconciliation_report}</pre>
                  ) : (
                    <pre className={styles.reportText}>{safeStringify(completion.reconciliation_report)}</pre>
                  )}
                </div>
              )}
              {completion.audit_trail != null && (
                <div className={styles.auditTrail}>
                  <h3>Audit trail</h3>
                  {typeof completion.audit_trail === 'string' ? (
                    <pre className={styles.auditText}>{completion.audit_trail}</pre>
                  ) : (
                    <>
                      {completion.audit_trail.extracted != null && (
                        <div className={styles.auditBlock}>
                          <h4 className={styles.auditSubhead}>Extracted</h4>
                          <pre className={styles.auditText}>{safeStringify(completion.audit_trail.extracted)}</pre>
                        </div>
                      )}
                      {(completion.audit_trail.assumptions || []).length > 0 && (
                        <div className={styles.auditBlock}>
                          <h4 className={styles.auditSubhead}>Assumptions</h4>
                          <ul className={styles.auditList}>
                            {completion.audit_trail.assumptions.map((a, i) => (
                              <li key={i}>{a}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {(completion.audit_trail.uncertainties || []).length > 0 && (
                        <div className={styles.auditBlock}>
                          <h4 className={styles.auditSubhead}>Uncertainties</h4>
                          <ul className={styles.auditList}>
                            {completion.audit_trail.uncertainties.map((u, i) => (
                              <li key={i}>{u}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {completion.audit_trail.decision_reasoning && (
                        <div className={styles.auditBlock}>
                          <h4 className={styles.auditSubhead}>Decision reasoning</h4>
                          <p className={styles.auditText}>{completion.audit_trail.decision_reasoning}</p>
                        </div>
                      )}
                      {(completion.audit_trail.llm_thoughts || []).length > 0 && (
                        <div className={styles.auditBlock}>
                          <h4 className={styles.auditSubhead}>LLM thoughts</h4>
                          <div className={styles.llmThoughts}>
                            {completion.audit_trail.llm_thoughts.map((entry, i) => (
                              <div key={i} className={styles.llmEntry}>
                                <span className={styles.llmPhase}>{entry.phase}{entry.step ? ` — ${entry.step}` : ''}</span>
                                {entry.thoughts && <pre className={styles.llmThoughtText}>{entry.thoughts}</pre>}
                                {entry.input_summary && <p className={styles.llmMeta}>Input: {entry.input_summary}</p>}
                                {entry.output_summary && <p className={styles.llmMeta}>Output: {entry.output_summary}</p>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className={styles.muted}>Loading completion…</p>
          )}
        </section>
      )}
    </div>
  );
}
