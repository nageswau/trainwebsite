// Shared local-upload/presign flow. The presigned path is only for a server in S3 mode (local-upload answers 400 "Use presigned S3
// upload"); any other refusal -- size, type, contents that do not match the type (nehn-003) -- is shown as the server worded it.
function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail)) return detail.map(item => item?.msg || "Invalid input").join("; ");
  return "The operation could not be completed.";
}

export async function uploadFile(file: File): Promise<string> {
  const local = new FormData();
  local.set("file", file);
  const localResponse = await fetch("/api/v1/files/local-upload", { method: "POST", body: local });
  if (localResponse.ok) return String((await localResponse.json()).url);
  if (localResponse.status !== 400) throw new Error(detailMessage((await localResponse.json().catch(() => ({}))).detail));
  const presignResponse = await fetch("/api/v1/files/presign", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: file.name, content_type: file.type, size: file.size }) });
  const signed = await presignResponse.json();
  if (!presignResponse.ok) throw new Error(detailMessage(signed.detail));
  const upload = await fetch(signed.upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
  if (!upload.ok) throw new Error("Object storage upload failed");
  return String(signed.key);
}
