export type ExtensionSchemaField = {
  key: string;
  type: string;
  label: string;
  help?: string;
  placeholder?: string;
  required?: boolean;
  default?: unknown;
  choices?: { value: string; label: string }[];
};

export function initialExtensionSettings(
  schema: { fields?: ExtensionSchemaField[] } | undefined,
  saved: Record<string, unknown> | undefined,
): Record<string, unknown> {
  return Object.fromEntries(
    (schema?.fields ?? []).map((field) => [
      field.key,
      field.type === "secret"
        ? ""
        : saved?.[field.key] ??
          field.default ??
          (field.type === "checkbox" ? false : field.type === "list" || field.type === "multiple_choice" ? [] : ""),
    ]),
  );
}

export function ExtensionSchemaForm({
  schema,
  values,
  setValue,
  onSubmit,
  working,
  submitLabel = "Save settings",
}: {
  schema: { fields?: ExtensionSchemaField[] };
  values: Record<string, unknown>;
  setValue: (key: string, value: unknown) => void;
  onSubmit: () => void;
  working: boolean;
  submitLabel?: string;
}) {
  if ((schema.fields?.length ?? 0) === 0) {
    return null;
  }
  return (
    <form
      className="browser-voice-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <h4>Settings</h4>
      {schema.fields!.map((field) => (
        <ExtensionSchemaFieldControl field={field} key={field.key} set={setValue} value={values[field.key]} />
      ))}
      <button className="browser-voice-submit" disabled={working} type="submit">
        {working ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}

function ExtensionSchemaFieldControl({
  field,
  value,
  set,
}: {
  field: ExtensionSchemaField;
  value: unknown;
  set: (key: string, value: unknown) => void;
}) {
  const selected = Array.isArray(value) ? value : [];
  return (
    <fieldset className="browser-voice-plugin-field">
      <legend>{field.label}</legend>
      {field.help ? <small>{field.help}</small> : null}
      {field.type === "secret" ? <small>Leave empty to keep the saved value.</small> : null}
      {field.type === "long_text" || field.type === "list" ? (
        <textarea
          onChange={(event) =>
            set(
              field.key,
              field.type === "list"
                ? event.target.value.split("\n").map((part) => part.trim()).filter(Boolean)
                : event.target.value,
            )
          }
          placeholder={field.placeholder}
          value={field.type === "list" ? selected.join("\n") : String(value ?? "")}
        />
      ) : null}
      {field.type === "choice" ? (
        <select onChange={(event) => set(field.key, event.target.value)} value={String(value ?? "")}>
          {field.choices?.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
      ) : null}
      {field.type === "multiple_choice" ? (
        <div>
          {field.choices?.map((choice) => (
            <label key={choice.value}>
              <input
                checked={selected.includes(choice.value)}
                onChange={(event) =>
                  set(
                    field.key,
                    event.target.checked
                      ? [...selected, choice.value]
                      : selected.filter((item) => item !== choice.value),
                  )
                }
                type="checkbox"
              />{" "}
              <span>{choice.label}</span>
            </label>
          ))}
        </div>
      ) : null}
      {field.type === "checkbox" ? (
        <label>
          <input checked={Boolean(value)} onChange={(event) => set(field.key, event.target.checked)} type="checkbox" />{" "}
          <span>On</span>
        </label>
      ) : null}
      {!["long_text", "list", "choice", "multiple_choice", "checkbox"].includes(field.type) ? (
        <input
          onChange={(event) =>
            set(field.key, field.type === "number" ? Number(event.target.value) : event.target.value)
          }
          placeholder={field.placeholder}
          required={field.required && field.type !== "secret"}
          type={field.type === "secret" ? "password" : field.type === "number" ? "number" : field.type === "url" ? "url" : "text"}
          value={String(value ?? "")}
        />
      ) : null}
    </fieldset>
  );
}
