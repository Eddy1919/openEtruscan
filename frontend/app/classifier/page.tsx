export default function ClassifierPage() {
  return (
    <div className="page-container" style={{ maxWidth: 700 }}>
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "2rem",
          marginBottom: "0.5rem",
        }}
      >
        Neural Classifier
      </h1>
      <p
        style={{
          color: "var(--text-secondary)",
          marginBottom: "2rem",
          lineHeight: 1.6,
        }}
      >
        Classify Etruscan inscriptions by type using a character-level CNN
        running entirely in your browser via ONNX Runtime Web.
      </p>
      <div
        className="card"
        style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}
      >
        <p style={{ fontSize: "2rem", marginBottom: "1rem" }}>🧠</p>
        <p>
          The ONNX classifier integration is coming soon.
          <br />
          Models are published on{" "}
          <a
            href="https://huggingface.co/Eddy1919/openetruscan-classifier"
            target="_blank"
            rel="noopener noreferrer"
          >
            Hugging Face ↗
          </a>
        </p>
      </div>
    </div>
  );
}
