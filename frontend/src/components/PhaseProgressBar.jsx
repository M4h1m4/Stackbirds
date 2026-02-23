import styles from './PhaseProgressBar.module.css';

const STEPS = ['Extraction', 'Matching', 'Completion'];

export default function PhaseProgressBar({ currentPhase }) {
  const currentIndex = STEPS.indexOf(currentPhase);
  const activeIndex = currentIndex >= 0 ? currentIndex : 0;
  const progressPercent = ((activeIndex + 1) / STEPS.length) * 100;

  return (
    <div className={styles.wrapper}>
      <div className={styles.barTrack}>
        <div
          className={styles.barFill}
          style={{ width: `${progressPercent}%` }}
          role="progressbar"
          aria-valuenow={Math.round(progressPercent)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Pipeline: ${currentPhase}`}
        />
      </div>
      <div className={styles.steps}>
        {STEPS.map((label, i) => (
          <div
            key={label}
            className={`${styles.step} ${i <= activeIndex ? styles.stepActive : ''} ${i === activeIndex ? styles.stepCurrent : ''}`}
          >
            <span className={styles.stepDot} />
            <span className={styles.stepLabel}>{label}</span>
          </div>
        ))}
      </div>
      <p className={styles.phaseName}>Current phase: <strong>{currentPhase}</strong></p>
    </div>
  );
}
