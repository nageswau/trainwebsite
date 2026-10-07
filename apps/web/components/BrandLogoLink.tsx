import Image from "next/image";
import Link from "next/link";

// The EduSphere logo (linking home) for standalone pages that render no SiteHeader/PortalShell --
// register, forgot/reset password, invite accept, BDM/telecaller sign-in and /account/privacy.
export default function BrandLogoLink() {
  return (
    <Link href="/" className="page-logo">
      <Image src="/brand/logo-light.png" width={1200} height={523} alt="EduSphere" priority />
    </Link>
  );
}
