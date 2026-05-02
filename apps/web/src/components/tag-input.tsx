"use client";

import { useState, type KeyboardEvent } from "react";

type TagInputProps = {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
};

export function TagInput({ value, onChange, placeholder, disabled }: TagInputProps) {
  const [input, setInput] = useState("");

  const addTags = (raw: string) => {
    const newTags = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (newTags.length === 0) return;
    const existing = new Set(value);
    const added = newTags.filter((t) => !existing.has(t));
    if (added.length > 0) {
      onChange([...value, ...added]);
    }
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTags(input);
    }
  };

  const handleBlur = () => {
    if (input.trim()) {
      addTags(input);
    }
  };

  const removeTag = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  return (
    <div className="tag-input-wrap">
      <div className="tag-input-tags">
        {value.map((tag) => (
          <span className="skill-tag" key={tag}>
            {tag}
            <button
              className="tag-remove"
              onClick={() => removeTag(tag)}
              disabled={disabled}
              title="Remove"
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <input
        type="text"
        className="tag-input-field"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        placeholder={placeholder ?? "Type and press Enter or comma to add..."}
        disabled={disabled}
      />
    </div>
  );
}
