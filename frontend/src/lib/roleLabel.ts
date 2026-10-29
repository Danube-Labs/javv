/** A role id as people read it: `security_lead` shows as "security lead". The id stays the value
 * that a form sends and the server stores (issue 1039). */
export function roleLabel(id: string): string {
  return id.replaceAll('_', ' ')
}
