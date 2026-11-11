"use client";
export default function ErrorBoundary({ reset }: { reset: () => void }) {
  return (
    <main id="main">
      <h1>Unable to load this page</h1>
      <p>Please try again.</p>
      <button onClick={reset}>Retry</button>
    </main>
  );
}
