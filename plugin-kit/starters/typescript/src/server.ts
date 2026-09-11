export function greeting(name = "there", configuredGreeting = "Hello") {
  const cleanName = name.trim().slice(0, 80) || "there";
  const cleanGreeting = configuredGreeting.trim().slice(0, 40) || "Hello";
  const message = `${cleanGreeting}, ${cleanName}!`;
  return {content: [{type: "text", text: message}], structuredContent: {message}};
}
