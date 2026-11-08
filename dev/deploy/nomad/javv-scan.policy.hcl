# Read-only access for the JAVV scan jobs: list the jobs and read their allocations in each namespace.
namespace "*" {
  capabilities = ["list-jobs", "read-job"]
}
