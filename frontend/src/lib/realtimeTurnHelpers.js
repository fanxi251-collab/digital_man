export function formatConfidence(value) {
  const number = Number(value);
  return Number.isNaN(number) ? "--" : `${Math.round(number * 100)}%`;
}

export function latestUserText(messages) {
  return [...(messages || [])]
    .reverse()
    .find((message) => (
      message?.role === "user"
      && String(message.content || "").trim()
    ))?.content?.trim() || "";
}

export function ensureAssistantMessage(messages, turnId, retryQuestion = "") {
  let message = messages.find((item) => item.id === turnId && item.role === "assistant");
  if (!message) {
    message = {
      id: turnId,
      role: "assistant",
      content: "",
      pending: true,
      retryQuestion,
    };
    messages.push(message);
  }
  if (retryQuestion && !message.retryQuestion) message.retryQuestion = retryQuestion;
  return message;
}

export function ensureVoiceMessages(messages, turnId, transcript) {
  if (!messages.some((message) => message.id === `${turnId}_user`)) {
    messages.push({ id: `${turnId}_user`, role: "user", content: transcript, voice: true });
  }
  return ensureAssistantMessage(messages, turnId, transcript);
}

export function applyFailedActiveMessage(messages, activeTurnId, message, retryable) {
  if (!activeTurnId) return;
  const target = ensureAssistantMessage(messages, activeTurnId);
  target.error = message;
  target.retryable = retryable;
  target.pending = false;
  if (!target.retryQuestion) {
    const targetIndex = messages.indexOf(target);
    target.retryQuestion = [...messages.slice(0, targetIndex)]
      .reverse()
      .find((item) => item.role === "user")?.content || "";
  }
}
