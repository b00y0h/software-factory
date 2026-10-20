# Factory backlog

`/factory next` runs the first unchecked item, ticks it, and records its job id after the
arrow. Write each item the way you'd brief a teammate: what, for whom, and how you'll know
it works. One item becomes one job, one branch and one PR.

<!--
Example, inside a comment so /factory next skips it:

- [ ] Rate-limit the public form submit endpoint: at most 10 submits per IP per minute,
      the 11th gets a 429 with a Retry-After header.
- [x] Add lastmod to the sitemap → 001-sitemap-lastmod
-->

