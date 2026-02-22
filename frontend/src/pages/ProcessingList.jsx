import { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { getProcessingList } from '../api';
import styles from './ProcessingList.module.css';

/**
 * Processing list. No upload — user enters inbox email to see processings (from unread emails in that inbox).
 */
export default function ProcessingList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const inboxFromUrl = searchParams.get('inbox_email') || searchParams.get('customer_id') || '';
  const [email, setEmail] = useState(inboxFromUrl);
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const byInbox = true;

  useEffect(() => {
    if (inboxFromUrl) setEmail(inboxFromUrl);
  }, [inboxFromUrl]);

  useEffect(() => {
    if (!email.trim()) {
      setList([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getProcessingList(email.trim(), { byInbox })
      .then((data) => {
        if (!cancelled) setList(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.body?.detail || err.message || 'Failed to load');
          setList([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [email, byInbox]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const value = email.trim();
    if (value) {
      setSearchParams({ inbox_email: value });
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Invoice processing</h1>
        <p className={styles.subtitle}>
          Invoices are loaded from your email inbox. Enter the email address that receives invoice emails to see processings and decisions.
        </p>
      </header>

      <form onSubmit={handleSubmit} className={styles.form}>
        <input
            type="text"
            placeholder="Your email (inbox that receives invoices)"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={styles.input}
            aria-label="Inbox email"
          />
        <button type="submit" className={styles.button}>Load</button>
      </form>

      {error && <div className={styles.error} role="alert">{error}</div>}
      {loading && <div className={styles.loading}>Loading…</div>}

      {!loading && !error && email.trim() && (
        <section className={styles.section}>
          <h2>Processings</h2>
          {list.length === 0 ? (
            <p className={styles.empty}>No processings found for this inbox. Send an email with a PDF invoice to this address and run the poller, then load again.</p>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Phase</th>
                  <th>Processing</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.processing_id}>
                    <td>{p.invoice_id}</td>
                    <td>{p.user_visible_phase}</td>
                    <td><code>{p.processing_id}</code></td>
                    <td>
                      <Link
                        to={`/processing/${p.processing_id}?inbox_email=${encodeURIComponent(email.trim())}`}
                        className={styles.link}
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
