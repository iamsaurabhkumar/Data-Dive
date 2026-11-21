import { redirect } from "next/navigation";

/** The production board moved to /kanban; keep old links working. */
export default function BoardRedirect() {
  redirect("/kanban");
}
