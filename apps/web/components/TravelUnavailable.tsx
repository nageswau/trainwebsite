import { accessUnavailable } from "@/components/AccessUnavailable";
import { ApiError } from "@/lib/api";

const ACCESS = new Set([401, 403, 404]);

// bdm-010 (§12.2 F6, review I2): a travel page whose read failed. Signed out, refused or not found is still the access card; a
// server error or a dropped connection is temporary, so it gets a Retry link back to the same page instead of an access message.
export function travelUnavailable(error: unknown, loginHref: string, retryHref: string) {
  if (error instanceof ApiError && ACCESS.has(error.status)) return accessUnavailable(error, loginHref);
  return (
    <div className="section">
      <div className="container card" role="alert">
        <h1>Travel is not available right now</h1>
        <p>We could not load this page. Your trips are safe; please try again.</p>
        <a className="btn" href={retryHref}>Retry</a>
      </div>
    </div>
  );
}

/** QA10-04: a malformed trip link reads exactly like an unknown trip. */
export const tripNotFound = (loginHref: string) => accessUnavailable(new ApiError("Trip not found", 404), loginHref);
