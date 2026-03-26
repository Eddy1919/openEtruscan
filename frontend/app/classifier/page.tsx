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
        Inscription Classifier
      </h1>
      <p
        style={{
          color: "var(--text-secondary)",
          marginBottom: "2rem",
          lineHeight: 1.6,
        }}
      >
        Classify Etruscan inscriptions by epigraphic type using character-level
        neural models. Inference runs entirely client-side via ONNX Runtime Web.
      </p>
      <div
        className="card"
        style={{ textAlign: "center", padding: "3rem", color: "var(--text-muted)" }}
      >
        <p style={{ marginBottom: "1rem", fontSize: "0.9rem" }}>
          The in-browser classifier is under active development.
        </p>
        <p style={{ fontSize: "0.85rem" }}>
          Pre-trained models are available on{" "}
          <a
            href="https://huggingface.co/Eddy1919/openetruscan-classifier"
            target="_blank"
            rel="noopener noreferrer"
          >
            Hugging Face
          </a>
          .
        </p>
      </div>
    </div>
  );
}
