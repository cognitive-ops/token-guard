import { redirect } from "next/navigation";

/** The dashboard suite opens on Overview. */
export default function Home() {
  redirect("/overview");
}
