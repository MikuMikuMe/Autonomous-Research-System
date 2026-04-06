import React, { useState } from "react";

interface Props {
  onSubmit: (idea: string) => void;
  disabled: boolean;
}

export const ResearchInput: React.FC<Props> = ({ onSubmit, disabled }) => {
  const [idea, setIdea] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (idea.trim()) onSubmit(idea.trim());
  };

  return (
    <form className="research-input" onSubmit={handleSubmit}>
      <textarea
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="Describe your research idea…"
        rows={4}
        disabled={disabled}
      />
      <div className="research-input__actions">
        <button type="submit" disabled={disabled || !idea.trim()}>
          {disabled ? "Running…" : "Start Research"}
        </button>
      </div>
    </form>
  );
};
