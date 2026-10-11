# Changelog

## [0.7.2](https://github.com/Danube-Labs/javv-poc/compare/v0.7.1...v0.7.2) (2026-10-11)


### Bug Fixes

* a fresh install can mint its first token and read its settings pages ([#820](https://github.com/Danube-Labs/javv-poc/issues/820)) ([436e91e](https://github.com/Danube-Labs/javv-poc/commit/436e91e265124da8a0f9e5eda35a55dcbb4750f0))
* a refused read no longer reads as an empty answer ([#821](https://github.com/Danube-Labs/javv-poc/issues/821)) ([601385e](https://github.com/Danube-Labs/javv-poc/commit/601385ef07521a0309f6326a49582d37f39ff356))
* scan pods started by digest through the pullable image_id reference ([#819](https://github.com/Danube-Labs/javv-poc/issues/819)) ([2b0e9c2](https://github.com/Danube-Labs/javv-poc/commit/2b0e9c2ee25f7171784bee309cb084987346381a))
* the primary button presses in with a ring ([#824](https://github.com/Danube-Labs/javv-poc/issues/824)) ([373254e](https://github.com/Danube-Labs/javv-poc/commit/373254e37217594c9171932d88aa4e175c826761))

## [0.7.1](https://github.com/Danube-Labs/javv-poc/compare/v0.7.0...v0.7.1) (2026-10-10)


### Bug Fixes

* a cluster or window change waits for the navigation under way ([#810](https://github.com/Danube-Labs/javv-poc/issues/810)) ([9727c39](https://github.com/Danube-Labs/javv-poc/commit/9727c395a365cefb7c52a863c74a2851074befcb))
* a session with a temporary password reaches only the password change, reads included ([#805](https://github.com/Danube-Labs/javv-poc/issues/805)) ([beb6ef2](https://github.com/Danube-Labs/javv-poc/commit/beb6ef2a692de7947b6eac9ca59a12a83eb00572))
* every read checks that an ok reply's body arrived, and a lost token value says so ([#813](https://github.com/Danube-Labs/javv-poc/issues/813)) ([5eec52e](https://github.com/Danube-Labs/javv-poc/commit/5eec52e7bd01095048ec944d76c074860b1995c8))
* overview reads survive an ok reply with no body, and logged errors say where they threw ([#812](https://github.com/Danube-Labs/javv-poc/issues/812)) ([4f36248](https://github.com/Danube-Labs/javv-poc/commit/4f3624854075b53aef5ef82b6622ec5510415fca))
* the rig login helpers read with the session the password change returns ([#808](https://github.com/Danube-Labs/javv-poc/issues/808)) ([a58e788](https://github.com/Danube-Labs/javv-poc/commit/a58e78810817b3a97e1ae7252293270b0b06e8e6))

## [0.7.0](https://github.com/Danube-Labs/javv-poc/compare/v0.6.3...v0.7.0) (2026-10-09)


### Features

* rename JAVV_TOKEN_PEPPER to JAVV_SECRET_KEY, and fix the docs site ([#795](https://github.com/Danube-Labs/javv-poc/issues/795)) ([2a78774](https://github.com/Danube-Labs/javv-poc/commit/2a78774d13537d887614c74d2977723f6fd0b420))


### Miscellaneous Chores

* each release publishes its docs version and latest, and m10 closes with 0.7.0 ([#798](https://github.com/Danube-Labs/javv-poc/issues/798)) ([2d7e158](https://github.com/Danube-Labs/javv-poc/commit/2d7e15839a8b6b3a771fca837dc4afcf56b09bbb))

## [0.6.3](https://github.com/Danube-Labs/javv-poc/compare/v0.6.2...v0.6.3) (2026-10-09)


### Bug Fixes

* **deps:** update dependency fastapi to &gt;=0.143,&lt;0.144 ([#783](https://github.com/Danube-Labs/javv-poc/issues/783)) ([5a23216](https://github.com/Danube-Labs/javv-poc/commit/5a23216f15cee6549f9bdadb9df8c62618ef6a4e))

## [0.6.2](https://github.com/Danube-Labs/javv-poc/compare/v0.6.1...v0.6.2) (2026-10-08)


### Features

* a countdown, a fleet chip and a bell notice before a silent cluster is retired ([#777](https://github.com/Danube-Labs/javv-poc/issues/777)) ([f6b2fcb](https://github.com/Danube-Labs/javv-poc/commit/f6b2fcbb66b87774aa9b01126890f3f6f4b0a81a))
* a reset command for a forgotten password when no admin can sign in ([#762](https://github.com/Danube-Labs/javv-poc/issues/762)) ([21ae542](https://github.com/Danube-Labs/javv-poc/commit/21ae5425a4cf8b440dfd47e17a17235ba0de9d6d))
* delete a retired cluster, everything but its audit rows, matched by its exact id ([#775](https://github.com/Danube-Labs/javv-poc/issues/775)) ([b483e27](https://github.com/Danube-Labs/javv-poc/commit/b483e2732f899b18b7ee81aed081bfc8e561676f))
* refuse bring back mid-delete, say a manual retire needs a new token, and recheck deletes ([#779](https://github.com/Danube-Labs/javv-poc/issues/779)) ([f868a07](https://github.com/Danube-Labs/javv-poc/commit/f868a07e91ee9ee1cefeb40dcd321d398b139b65))
* retire silent clusters automatically or by hand, off the cluster list with their data kept ([#768](https://github.com/Danube-Labs/javv-poc/issues/768)) ([6579ff0](https://github.com/Danube-Labs/javv-poc/commit/6579ff0e7b53dcca87972ed9a40a83ae9a551e5b))
* retire, bring back and delete clusters, and the retirement window, in settings cluster ([#776](https://github.com/Danube-Labs/javv-poc/issues/776)) ([ae186a8](https://github.com/Danube-Labs/javv-poc/commit/ae186a835b3c12a29a7a62ca6d29282b2c5f8be1))
* the sign-in screen says what to do about a forgotten password ([#763](https://github.com/Danube-Labs/javv-poc/issues/763)) ([2aed81e](https://github.com/Danube-Labs/javv-poc/commit/2aed81e4c240353b119ec3a49fac3df19edfe044))


### Bug Fixes

* drop minio from the dev seed, since docker hub no longer serves its pinned tag ([#767](https://github.com/Danube-Labs/javv-poc/issues/767)) ([49a5c55](https://github.com/Danube-Labs/javv-poc/commit/49a5c55bc57486a55c2fbf4ab50b3e3155640311))

## [0.6.1](https://github.com/Danube-Labs/javv-poc/compare/v0.6.0...v0.6.1) (2026-10-06)


### Bug Fixes

* the release smoke sets every compose secret, and the release pr gets its chart readmes ([#753](https://github.com/Danube-Labs/javv-poc/issues/753)) ([1299ad8](https://github.com/Danube-Labs/javv-poc/commit/1299ad81e2d022534b4625ede5bd7c06ff5b9853))

## [0.6.0](https://github.com/Danube-Labs/javv-poc/compare/v0.5.1...v0.6.0) (2026-10-06)


### Features

* a release publishes the three charts to ghcr, signed ([#743](https://github.com/Danube-Labs/javv-poc/issues/743)) ([e04ab83](https://github.com/Danube-Labs/javv-poc/commit/e04ab83c83074df95c4dbd096682754833ccd088))
* compose runs opensearch with its login on ([#733](https://github.com/Danube-Labs/javv-poc/issues/733)) ([6c5ed35](https://github.com/Danube-Labs/javv-poc/commit/6c5ed3595573a25bcb5b5577d39189d2c49195f4))
* the backend signs in to a secured opensearch, through one client factory ([#731](https://github.com/Danube-Labs/javv-poc/issues/731)) ([de2a875](https://github.com/Danube-Labs/javv-poc/commit/de2a87551299c557fec104b761ba26b1a1163e49))
* the backend signs in to opensearch as javv, a least-privilege role ([#745](https://github.com/Danube-Labs/javv-poc/issues/745)) ([9613caf](https://github.com/Danube-Labs/javv-poc/commit/9613caf2eaa8943eb7911eafa8f5f424f264622a))
* the charts create the javv user and role, and the app signs in as it ([#748](https://github.com/Danube-Labs/javv-poc/issues/748)) ([498e7a8](https://github.com/Danube-Labs/javv-poc/commit/498e7a8f99fc6ee3ad82d955656d5f25130a0176))
* the javv chart, the backend and frontend from the compose file ([#740](https://github.com/Danube-Labs/javv-poc/issues/740)) ([db1d615](https://github.com/Danube-Labs/javv-poc/commit/db1d6158390f3dbc81f6cabebc2be31d3b02e166))
* the javv-opensearch chart, opensearch with its login on and admin alone ([#738](https://github.com/Danube-Labs/javv-poc/issues/738)) ([1b51647](https://github.com/Danube-Labs/javv-poc/commit/1b516470f2361802b62d3f12534a82f066c07e23))
* the javv-scanner chart, a cronjob and a vuln-db cache per scanner ([#741](https://github.com/Danube-Labs/javv-poc/issues/741)) ([63bc658](https://github.com/Danube-Labs/javv-poc/commit/63bc658bca7758d6211d3a02ec141c995f67daa3))
* the release signs the app images, with an sbom attestation ([#742](https://github.com/Danube-Labs/javv-poc/issues/742)) ([6568349](https://github.com/Danube-Labs/javv-poc/commit/65683499ecd197ee063ea20c7120b4dca431d39c))


### Bug Fixes

* compose's opensearch starts with admin as its only user ([#737](https://github.com/Danube-Labs/javv-poc/issues/737)) ([f545e9d](https://github.com/Danube-Labs/javv-poc/commit/f545e9d074de6668156b92df906893b3a521f729))
* the charts ci step fails on a failed render or a missing image ([#744](https://github.com/Danube-Labs/javv-poc/issues/744)) ([6f4e336](https://github.com/Danube-Labs/javv-poc/commit/6f4e33600e8f29b70bd8ec15f43605b20d7440ed))
* the password change says the 12-character rule and why a password was refused ([#727](https://github.com/Danube-Labs/javv-poc/issues/727)) ([4a86e81](https://github.com/Danube-Labs/javv-poc/commit/4a86e8107351038c0797d95cc5eaf7d9b5c4dafb))


### Miscellaneous Chores

* cut the 0.6.0 minor release ([#751](https://github.com/Danube-Labs/javv-poc/issues/751)) ([5c572ad](https://github.com/Danube-Labs/javv-poc/commit/5c572ad3009fb05ff7d8beb02fc6f648b22d3871))

## [0.5.1](https://github.com/Danube-Labs/javv-poc/compare/v0.5.0...v0.5.1) (2026-10-04)


### Features

* a release publishes the app images, and the compose file runs them ([#723](https://github.com/Danube-Labs/javv-poc/issues/723)) ([dad731f](https://github.com/Danube-Labs/javv-poc/commit/dad731f63e6ecab05dc531f63920ae1d8dc0d6b7))
* docker compose runs the whole stack on one machine, with a deploy guide ([#720](https://github.com/Danube-Labs/javv-poc/issues/720)) ([e831ce0](https://github.com/Danube-Labs/javv-poc/commit/e831ce019832cb480a995d513831652554b5635f))
* the backend image, and a setting for the session cookie's Secure flag ([#716](https://github.com/Danube-Labs/javv-poc/issues/716)) ([bbd55cf](https://github.com/Danube-Labs/javv-poc/commit/bbd55cf81095ef028229582b6e670da61fa88ada))
* the frontend image, with a server that serves the app and forwards to the backend ([#718](https://github.com/Danube-Labs/javv-poc/issues/718)) ([31a34df](https://github.com/Danube-Labs/javv-poc/commit/31a34dfd1b356928ac131c09a82b49235ff19704))

## [0.5.0](https://github.com/Danube-Labs/javv-poc/compare/v0.4.13...v0.5.0) (2026-10-03)


### Features

* a crash page inside the frame, and a static maintenance page ([#688](https://github.com/Danube-Labs/javv-poc/issues/688)) ([8f89011](https://github.com/Danube-Labs/javv-poc/commit/8f89011a79979f57f4b6e64ea5938afd9679a410))
* one registry and one lease for every background job, the schedule maths and the scheduler settings ([#692](https://github.com/Danube-Labs/javv-poc/issues/692)) ([87a704f](https://github.com/Danube-Labs/javv-poc/commit/87a704f0cd0c16f019f824a9fc64b17ad99ca98f))
* the audit log opens without sign-ins, and a triage change can be undone ([#686](https://github.com/Danube-Labs/javv-poc/issues/686)) ([e03213a](https://github.com/Danube-Labs/javv-poc/commit/e03213ae968ed3591668a1cf45ce369194573c2c))
* the backend runs its own background jobs on cron schedules ([#693](https://github.com/Danube-Labs/javv-poc/issues/693)) ([f637fed](https://github.com/Danube-Labs/javv-poc/commit/f637fed0c67946f81bd9d2391b9b8b2fb731bdd8))
* the Guide explains a state against a risk acceptance, and the Approval list ([#700](https://github.com/Danube-Labs/javv-poc/issues/700)) ([f0b15ba](https://github.com/Danube-Labs/javv-poc/commit/f0b15baa21bc96f948d66e091d45a65a99ed35bf)), closes [#698](https://github.com/Danube-Labs/javv-poc/issues/698)
* the job cards on the Data inspector become one table with column headers ([#696](https://github.com/Danube-Labs/javv-poc/issues/696)) ([2a9eb30](https://github.com/Danube-Labs/javv-poc/commit/2a9eb303d500896ff26aade7508871c5818c6e56))
* the jobs route lists every background job with its schedule and health ([#694](https://github.com/Danube-Labs/javv-poc/issues/694)) ([9721e64](https://github.com/Danube-Labs/javv-poc/commit/9721e64082f2a0610e281a21d1e2df90e5e34f69))
* the Scheduled jobs card on the Data inspector, with a status chip per job ([#695](https://github.com/Danube-Labs/javv-poc/issues/695)) ([71c3df8](https://github.com/Danube-Labs/javv-poc/commit/71c3df8af331b677c475c307c31d7f533a6f3e9d))


### Bug Fixes

* a dead backend is reported as the server, not as a wrong password or OpenSearch ([#689](https://github.com/Danube-Labs/javv-poc/issues/689)) ([a4493bb](https://github.com/Danube-Labs/javv-poc/commit/a4493bb925a24d100e3100c15d8cb9f3b0a232f4))
* an image that cannot be scanned no longer freezes the running-images view ([#690](https://github.com/Danube-Labs/javv-poc/issues/690)) ([ccc52ab](https://github.com/Danube-Labs/javv-poc/commit/ccc52abc2c1921955f2076f540a7e7e2dbc2ea24))
* expiry stored in UTC, lifecycle errors fail the run, jobs list needs the inspect permission ([#709](https://github.com/Danube-Labs/javv-poc/issues/709)) ([567e73e](https://github.com/Danube-Labs/javv-poc/commit/567e73e189772bef2d0f67a838f8d5dfa3469d70))
* small findings from the design review (wording, headings, scope legend, empty pager) ([#685](https://github.com/Danube-Labs/javv-poc/issues/685)) ([2fa5d7c](https://github.com/Danube-Labs/javv-poc/commit/2fa5d7c3e619cf371f5e554c34be38a096197879))
* stale survives decision re-projection, and token rotation no longer mass-stales ([#708](https://github.com/Danube-Labs/javv-poc/issues/708)) ([87fec5f](https://github.com/Danube-Labs/javv-poc/commit/87fec5f9c61a98d886b86fc137a7cf707571b737))


### Miscellaneous Chores

* cut the 0.5.0 minor release ([#713](https://github.com/Danube-Labs/javv-poc/issues/713)) ([01b8018](https://github.com/Danube-Labs/javv-poc/commit/01b8018cc568ea6695fbf9c3eae048b772dae7b4))

## [0.4.13](https://github.com/Danube-Labs/javv-poc/compare/v0.4.12...v0.4.13) (2026-10-02)


### Bug Fixes

* three layout glitches (settings tabs and image detail at 1024, empty trend chart) ([#682](https://github.com/Danube-Labs/javv-poc/issues/682)) ([0b86ea5](https://github.com/Danube-Labs/javv-poc/commit/0b86ea51b54838b9e88b5eada07ae8090894a742))

## [0.4.12](https://github.com/Danube-Labs/javv-poc/compare/v0.4.11...v0.4.12) (2026-10-02)


### Bug Fixes

* filters and labels say things by their display names, not the stored values ([#678](https://github.com/Danube-Labs/javv-poc/issues/678)) ([a3acb86](https://github.com/Danube-Labs/javv-poc/commit/a3acb86ec92e31a3510d71d501a220b49749f7da))
* open any table row from the keyboard, through a real link on its identifier ([#677](https://github.com/Danube-Labs/javv-poc/issues/677)) ([f9fe4c1](https://github.com/Danube-Labs/javv-poc/commit/f9fe4c1bfe6938cd7a05b4147c84caa4a593e513)), closes [#674](https://github.com/Danube-Labs/javv-poc/issues/674)

## [0.4.11](https://github.com/Danube-Labs/javv-poc/compare/v0.4.10...v0.4.11) (2026-10-02)


### Bug Fixes

* a page for unknown addresses, named settings inputs, and a bulk triage dialog that helps ([#676](https://github.com/Danube-Labs/javv-poc/issues/676)) ([38c8a87](https://github.com/Danube-Labs/javv-poc/commit/38c8a8754860b9e9efa3d85de7debaec77131b7d)), closes [#674](https://github.com/Danube-Labs/javv-poc/issues/674)
* give status its own colours, one caution amber, and ramps that read in grayscale ([#673](https://github.com/Danube-Labs/javv-poc/issues/673)) ([f9b9bfe](https://github.com/Danube-Labs/javv-poc/commit/f9b9bfef0302a956b081da771a22d0022c675fc8)), closes [#659](https://github.com/Danube-Labs/javv-poc/issues/659)
* open the clicked cluster or saved view on the first click, and gate it in the smoke ([#668](https://github.com/Danube-Labs/javv-poc/issues/668)) ([60ff430](https://github.com/Danube-Labs/javv-poc/commit/60ff43093d2b52b4efdd7a6fd40e123de74aac40)), closes [#666](https://github.com/Danube-Labs/javv-poc/issues/666)

## [0.4.10](https://github.com/Danube-Labs/javv-poc/compare/v0.4.9...v0.4.10) (2026-10-01)


### Bug Fixes

* drop internal decision codes from ui copy and say why instead ([#665](https://github.com/Danube-Labs/javv-poc/issues/665)) ([c97d998](https://github.com/Danube-Labs/javv-poc/commit/c97d998ea2cd7522643af40a4ef98dd9e8b07693))
* no em dashes in copy, one muted hyphen for empty values, and a test that keeps it so ([#661](https://github.com/Danube-Labs/javv-poc/issues/661)) ([0b283f5](https://github.com/Danube-Labs/javv-poc/commit/0b283f59c6c8a8e012b7da327313c525c9c95281)), closes [#652](https://github.com/Danube-Labs/javv-poc/issues/652)

## [0.4.9](https://github.com/Danube-Labs/javv-poc/compare/v0.4.8...v0.4.9) (2026-10-01)


### Bug Fixes

* fit every screen at 1024, 1366 and 1920, and check it in the visual rig ([#658](https://github.com/Danube-Labs/javv-poc/issues/658)) ([af5d9ff](https://github.com/Danube-Labs/javv-poc/commit/af5d9ff64bfeec7c72ca5bb2f2104d3c396a4b2a))
* say when the scanner freshness check fails instead of staying silent ([#656](https://github.com/Danube-Labs/javv-poc/issues/656)) ([4940288](https://github.com/Danube-Labs/javv-poc/commit/49402888f881cc2c734697e9f758c1c0e43f031a))

## [0.4.8](https://github.com/Danube-Labs/javv-poc/compare/v0.4.7...v0.4.8) (2026-10-01)


### Features

* add a push mode to the scanner compatibility gate ([#636](https://github.com/Danube-Labs/javv-poc/issues/636)) ([e57ee58](https://github.com/Danube-Labs/javv-poc/commit/e57ee5801687b0be197e7c6dca5cb115e5fca77f)), closes [#631](https://github.com/Danube-Labs/javv-poc/issues/631)
* add the about page with the running stack, diagnostics and docs links ([#648](https://github.com/Danube-Labs/javv-poc/issues/648)) ([d2957f9](https://github.com/Danube-Labs/javv-poc/commit/d2957f96a971d3a55f289c89202c1f36cb7436c1))
* add the guide page, how to read javv, and split it from about ([#653](https://github.com/Danube-Labs/javv-poc/issues/653)) ([83180f6](https://github.com/Danube-Labs/javv-poc/commit/83180f6b8f2e54219b092f19d85f48a216a70ac3))
* check every scanner version's real push against the store in ci ([#638](https://github.com/Danube-Labs/javv-poc/issues/638)) ([77f3cfd](https://github.com/Danube-Labs/javv-poc/commit/77f3cfd70a0c4e2ea46cfe8a3cd274e7f65f208c)), closes [#631](https://github.com/Danube-Labs/javv-poc/issues/631)
* link the freshness banner and the ingest strip to the guide ([#654](https://github.com/Danube-Labs/javv-poc/issues/654)) ([e4b8d61](https://github.com/Danube-Labs/javv-poc/commit/e4b8d61d07ad7c3aa52ac6be1811d567573b4a0c))
* report the running version on /api/v1/meta and in the bootstrap log ([#629](https://github.com/Danube-Labs/javv-poc/issues/629)) ([77d5581](https://github.com/Danube-Labs/javv-poc/commit/77d558124e23d02bddfdbc919f33f12a723f5073)), closes [#261](https://github.com/Danube-Labs/javv-poc/issues/261)
* show the running versions in the sidebar footer ([#635](https://github.com/Danube-Labs/javv-poc/issues/635)) ([d626230](https://github.com/Danube-Labs/javv-poc/commit/d62623027c60c44b937144a214a4962d28a7a220)), closes [#261](https://github.com/Danube-Labs/javv-poc/issues/261)


### Bug Fixes

* carry the request's id on every error response and crash log line ([#645](https://github.com/Danube-Labs/javv-poc/issues/645)) ([64a3d16](https://github.com/Danube-Labs/javv-poc/commit/64a3d168b56268703168814d7ac53923cfa99d25))
* **deps:** update dependency fastapi to &gt;=0.141,&lt;0.142 ([#626](https://github.com/Danube-Labs/javv-poc/issues/626)) ([89240c7](https://github.com/Danube-Labs/javv-poc/commit/89240c795662ee6786e89fa89857a53859958370))
* drift-check the docs that state the supported scanner versions ([#642](https://github.com/Danube-Labs/javv-poc/issues/642)) ([64f500f](https://github.com/Danube-Labs/javv-poc/commit/64f500ff585af7e84ceea44986c01e909996a0a8))
* keep the release version out of the pinned openapi snapshot ([#655](https://github.com/Danube-Labs/javv-poc/issues/655)) ([8a81048](https://github.com/Danube-Labs/javv-poc/commit/8a810481c8408ca6c34bae71dddcf8e8dc02adf5))
* pin docker digests in dockerfiles only, not in .python-version ([#618](https://github.com/Danube-Labs/javv-poc/issues/618)) ([69e3641](https://github.com/Danube-Labs/javv-poc/commit/69e36417c66d01a89a5fd05942515ff4ca623479))
* read stored settings leniently so a rollback can read settings a newer release saved ([#643](https://github.com/Danube-Labs/javv-poc/issues/643)) ([88b595f](https://github.com/Danube-Labs/javv-poc/commit/88b595fb92d7ed4f86ebff0a94e82bd56f621b56))
* run the scanner images as a non-root user on a read-only-ready filesystem ([#634](https://github.com/Danube-Labs/javv-poc/issues/634)) ([f21d81d](https://github.com/Danube-Labs/javv-poc/commit/f21d81dfefe8f95f108442306ae0308588b53393)), closes [#632](https://github.com/Danube-Labs/javv-poc/issues/632)

## [0.4.7](https://github.com/Danube-Labs/javv-poc/compare/v0.4.6...v0.4.7) (2026-09-29)


### Features

* sign the published scanner images with cosign keyless and attest their sboms ([#611](https://github.com/Danube-Labs/javv-poc/issues/611)) ([ab0e6d4](https://github.com/Danube-Labs/javv-poc/commit/ab0e6d4c9e6e79f759056dfbe6d7521ef076f995)), closes [#74](https://github.com/Danube-Labs/javv-poc/issues/74)

## [0.4.6](https://github.com/Danube-Labs/javv-poc/compare/v0.4.5...v0.4.6) (2026-09-27)


### Features

* **backend:** client-events beacon endpoint with namespaced re-emit (issue 453) ([#517](https://github.com/Danube-Labs/javv-poc/issues/517)) ([0e32e0a](https://github.com/Danube-Labs/javv-poc/commit/0e32e0add053b5be8f9c95ff6ec6c3d5b5e8d4db)), closes [#453](https://github.com/Danube-Labs/javv-poc/issues/453)
* **backend:** count refused pushes per day per scanner ([#578](https://github.com/Danube-Labs/javv-poc/issues/578)) ([2361acc](https://github.com/Danube-Labs/javv-poc/commit/2361acc5a386e559a4c72e779d9dace9283cbcce)), closes [#575](https://github.com/Danube-Labs/javv-poc/issues/575)
* **backend:** read one scanner's failed ingests, newest first ([#573](https://github.com/Danube-Labs/javv-poc/issues/573)) ([ca49e69](https://github.com/Danube-Labs/javv-poc/commit/ca49e69ae72b6e6f5b1b112bf2818d86ae53d77e)), closes [#357](https://github.com/Danube-Labs/javv-poc/issues/357)
* **backend:** record ingests rejected past the token check, with lifecycle retention ([#572](https://github.com/Danube-Labs/javv-poc/issues/572)) ([2109af7](https://github.com/Danube-Labs/javv-poc/commit/2109af7ae9410c34f6f01e4a92dc078ffb259d4a)), closes [#357](https://github.com/Danube-Labs/javv-poc/issues/357)
* **backend:** sweep expired login sessions past a grace window ([#558](https://github.com/Danube-Labs/javv-poc/issues/558)) ([4ee2ff2](https://github.com/Danube-Labs/javv-poc/commit/4ee2ff2905646fb0dbeda047911185b2ce7070f1)), closes [#532](https://github.com/Danube-Labs/javv-poc/issues/532)
* **frontend:** report dropped beacon events and clip oversized field values (issue 519) ([#521](https://github.com/Danube-Labs/javv-poc/issues/521)) ([cf3f5a0](https://github.com/Danube-Labs/javv-poc/commit/cf3f5a0de886f18cd67844385dcf3bdd00e525eb))
* **frontend:** ship warn/error to the client-events beacon from lib/logger (issue 453) ([#518](https://github.com/Danube-Labs/javv-poc/issues/518)) ([bc44c4a](https://github.com/Danube-Labs/javv-poc/commit/bc44c4ab3913a9ee195666868822b470250c9cce))
* **frontend:** show each scanner's failed ingests on scanner status ([#574](https://github.com/Danube-Labs/javv-poc/issues/574)) ([53d9abd](https://github.com/Danube-Labs/javv-poc/commit/53d9abd556f8a0d256ccfcf08d5fe596c319c715)), closes [#357](https://github.com/Danube-Labs/javv-poc/issues/357)
* **frontend:** show refused pushes per day under scan ingest ([#579](https://github.com/Danube-Labs/javv-poc/issues/579)) ([550e331](https://github.com/Danube-Labs/javv-poc/commit/550e331f685f8bdda170d4e2f1f59f7211ee4f80)), closes [#575](https://github.com/Danube-Labs/javv-poc/issues/575)
* **ui:** recent sign-ins lens link on the users panel (issue 460 §2) ([#514](https://github.com/Danube-Labs/javv-poc/issues/514)) ([560b71f](https://github.com/Danube-Labs/javv-poc/commit/560b71fff9e1b46bc706f565f19e672966af55ec)), closes [#460](https://github.com/Danube-Labs/javv-poc/issues/460)


### Bug Fixes

* **backend:** clear the stale flag once a scan confirms the finding gone ([#580](https://github.com/Danube-Labs/javv-poc/issues/580)) ([f2cc037](https://github.com/Danube-Labs/javv-poc/commit/f2cc037a057849859d484edf2674e9c76fad5cd0)), closes [#576](https://github.com/Danube-Labs/javv-poc/issues/576)
* **backend:** drop test index templates with their indices ([#581](https://github.com/Danube-Labs/javv-poc/issues/581)) ([08782e2](https://github.com/Danube-Labs/javv-poc/commit/08782e2528e36a97767c808524eec5103314234d)), closes [#550](https://github.com/Danube-Labs/javv-poc/issues/550)
* **backend:** log a warning on capped and rejected paths that only bumped a metric ([#562](https://github.com/Danube-Labs/javv-poc/issues/562)) ([3722df8](https://github.com/Danube-Labs/javv-poc/commit/3722df83d41afaf5508dce12b783a029e51a74bc)), closes [#523](https://github.com/Danube-Labs/javv-poc/issues/523)
* **backend:** show fleet-wide audit rows on the audit log page ([#561](https://github.com/Danube-Labs/javv-poc/issues/561)) ([1dfae86](https://github.com/Danube-Labs/javv-poc/commit/1dfae868f96aa0e698e665ee27f156f0e48d2d7f)), closes [#559](https://github.com/Danube-Labs/javv-poc/issues/559)
* **backend:** wait out the reclaimed job in its test, and log an unrecordable job ending ([#570](https://github.com/Danube-Labs/javv-poc/issues/570)) ([e7cc2fd](https://github.com/Danube-Labs/javv-poc/commit/e7cc2fdde70ebb8b76136940564920735e3d7e65)), closes [#566](https://github.com/Danube-Labs/javv-poc/issues/566)
* **e2e:** metrics assertions fired on bodies that carried the counter ([#528](https://github.com/Danube-Labs/javv-poc/issues/528)) ([dff5243](https://github.com/Danube-Labs/javv-poc/commit/dff5243db3e74174f5a3ca35c9f188cef51ff9d4))
* **frontend:** guard beacon event names at build time and mark clipped values ([#569](https://github.com/Danube-Labs/javv-poc/issues/569)) ([75b61bc](https://github.com/Danube-Labs/javv-poc/commit/75b61bcfc15a74dd649b61b061f96138ca2a9f5b)), closes [#525](https://github.com/Danube-Labs/javv-poc/issues/525)
* render exception tracebacks in json logs and redact them ([#590](https://github.com/Danube-Labs/javv-poc/issues/590)) ([e71c509](https://github.com/Danube-Labs/javv-poc/commit/e71c509ba4f869ec4ef604c69a9f59bbf450d41f)), closes [#589](https://github.com/Danube-Labs/javv-poc/issues/589)

## [0.4.5](https://github.com/Danube-Labs/javv-poc/compare/v0.4.4...v0.4.5) (2026-07-30)


### Features

* approvals queue CSV export ([#359](https://github.com/Danube-Labs/javv-poc/issues/359), absorbing [#373](https://github.com/Danube-Labs/javv-poc/issues/373)) ([#507](https://github.com/Danube-Labs/javv-poc/issues/507)) ([b39c410](https://github.com/Danube-Labs/javv-poc/commit/b39c410232290dbabbd136998d9d9ecd30c8dea3))
* contributors leaderboard CSV export ([#359](https://github.com/Danube-Labs/javv-poc/issues/359)) ([#506](https://github.com/Danube-Labs/javv-poc/issues/506)) ([0d63037](https://github.com/Danube-Labs/javv-poc/commit/0d630372a5606e2fc972df247693e24d2a640139))
* package_name filter and the cve/package exclude twins ([#492](https://github.com/Danube-Labs/javv-poc/issues/492)) ([#501](https://github.com/Danube-Labs/javv-poc/issues/501)) ([0d5933d](https://github.com/Danube-Labs/javv-poc/commit/0d5933d4bafd1b74c6f321183ab2c2c48bfb3aea))
* **ui:** click to exclude a value from the rail and the grids ([#349](https://github.com/Danube-Labs/javv-poc/issues/349) §2) ([#491](https://github.com/Danube-Labs/javv-poc/issues/491)) ([19697a5](https://github.com/Danube-Labs/javv-poc/commit/19697a5de3a8ea4e9c5309ba352ddb1c55bf7fef))


### Bug Fixes

* **backend:** close the two pit-leak windows outside the reclaim guards ([#512](https://github.com/Danube-Labs/javv-poc/issues/512)) ([5cb14a1](https://github.com/Danube-Labs/javv-poc/commit/5cb14a12bf7aa8be727f6b5dc9f5030f9365043f)), closes [#509](https://github.com/Danube-Labs/javv-poc/issues/509)
* **backend:** drain the commit race from both sides, not just the retry count ([#513](https://github.com/Danube-Labs/javv-poc/issues/513)) ([795493a](https://github.com/Danube-Labs/javv-poc/commit/795493acfccaf51e2463907e76a3b8c0e80603b8)), closes [#510](https://github.com/Danube-Labs/javv-poc/issues/510)
* **frontend:** one csv-export path with try/finally: no more strandable buttons (issue 509) ([#511](https://github.com/Danube-Labs/javv-poc/issues/511)) ([25e794b](https://github.com/Danube-Labs/javv-poc/commit/25e794bcaa969137b5687adb153f3fc9028a8055)), closes [#509](https://github.com/Danube-Labs/javv-poc/issues/509)
* **frontend:** stop the dev server watching the gitignored coverage dir ([#504](https://github.com/Danube-Labs/javv-poc/issues/504)) ([ea04931](https://github.com/Danube-Labs/javv-poc/commit/ea04931c5af6a2bc0082e08030deead96e4c167a)), closes [#502](https://github.com/Danube-Labs/javv-poc/issues/502)
* **ui:** epss and mix bar tracks move onto --meter-track ([#498](https://github.com/Danube-Labs/javv-poc/issues/498)) ([c93ce7c](https://github.com/Danube-Labs/javv-poc/commit/c93ce7c90a3eb8098a26aac97983994836883286))
* **ui:** facet rail collapses long groups behind a show-all expander ([#500](https://github.com/Danube-Labs/javv-poc/issues/500)) ([ffd0544](https://github.com/Danube-Labs/javv-poc/commit/ffd05448adb7f69e15995815447d9550d00e280c))
* **ui:** make the grid value bar reachable, legible and pixel-crisp ([#496](https://github.com/Danube-Labs/javv-poc/issues/496)) ([9d559fb](https://github.com/Danube-Labs/javv-poc/commit/9d559fbb78c4fd9b4bd4de96650fac35760f8b41))
* **ui:** the two impeccable findings: a real layout animation and a phantom ([#495](https://github.com/Danube-Labs/javv-poc/issues/495)) ([ee05668](https://github.com/Danube-Labs/javv-poc/commit/ee05668e6a81847d85978035522189831a969212))

## [0.4.4](https://github.com/Danube-Labs/javv-poc/compare/v0.4.3...v0.4.4) (2026-07-27)


### Features

* filter findings nobody owns: the unassigned flag ([#349](https://github.com/Danube-Labs/javv-poc/issues/349) §1) ([#488](https://github.com/Danube-Labs/javv-poc/issues/488)) ([674cd33](https://github.com/Danube-Labs/javv-poc/commit/674cd33e09655508049e8d13521bb85a30bd297a))
* filter negation swept to running images, the audit trail and approvals ([#487](https://github.com/Danube-Labs/javv-poc/issues/487)) ([e89ee6e](https://github.com/Danube-Labs/javv-poc/commit/e89ee6ed86fa2b771186cc027853ee6a801832bc))


### Bug Fixes

* **ui:** five read-legibility defects: width, severity mix, dead column, bare counts, false empty states ([#486](https://github.com/Danube-Labs/javv-poc/issues/486)) ([e5aeaad](https://github.com/Danube-Labs/javv-poc/commit/e5aeaadd3cda29efca192c4e40e2f4bea3d4b1ab))

## [0.4.3](https://github.com/Danube-Labs/javv-poc/compare/v0.4.2...v0.4.3) (2026-07-26)


### Bug Fixes

* **scanner:** assert the cluster reached matches JAVV_CLUSTER_ID ([#472](https://github.com/Danube-Labs/javv-poc/issues/472)) ([b51d7bb](https://github.com/Danube-Labs/javv-poc/commit/b51d7bb33db79c4d846b4f1cc2b1df021b4e9eb5)), closes [#470](https://github.com/Danube-Labs/javv-poc/issues/470)

## [0.4.2](https://github.com/Danube-Labs/javv-poc/compare/v0.4.1...v0.4.2) (2026-07-19)


### Features

* **backend:** system-jobs lease guards both doors + lifecycle dry-run ([#464](https://github.com/Danube-Labs/javv-poc/issues/464)) ([9494d6a](https://github.com/Danube-Labs/javv-poc/commit/9494d6a3abc2d3b9f74500790ed5ca3e11ec12de))
* **ui:** dry run button on the lifecycle repair row ([#465](https://github.com/Danube-Labs/javv-poc/issues/465)) ([1b99e82](https://github.com/Danube-Labs/javv-poc/commit/1b99e82031ec05859841431b8244ac6c82fc4a06))


### Bug Fixes

* **ui:** audit table: detail shrinks to content, target owns the slack ([#462](https://github.com/Danube-Labs/javv-poc/issues/462)) ([d733424](https://github.com/Danube-Labs/javv-poc/commit/d7334246a2379fa7085106cf63eecb33b826d018))

## [0.4.1](https://github.com/Danube-Labs/javv-poc/compare/v0.4.0...v0.4.1) (2026-07-18)


### Features

* **backend:** repair-actions job surface: 202 triggers + lease/status ([#406](https://github.com/Danube-Labs/javv-poc/issues/406) follow-up) ([af2e7fb](https://github.com/Danube-Labs/javv-poc/commit/af2e7fb7f785e0932f8b6a8a2dbf27660aa236bb))
* **backend:** repair-actions surface: trigger the sanctioned jobs over http (issue 406) ([142827d](https://github.com/Danube-Labs/javv-poc/commit/142827dabd7de174d4ab18fd3789a04a8f972c96)), closes [#406](https://github.com/Danube-Labs/javv-poc/issues/406)
* data inspector: read-only store console ([#406](https://github.com/Danube-Labs/javv-poc/issues/406)) ([#455](https://github.com/Danube-Labs/javv-poc/issues/455)) ([3e2a787](https://github.com/Danube-Labs/javv-poc/commit/3e2a7873513991822638714bddf8cb0ef5785503))
* **ui:** repair actions card on /inspect ([#406](https://github.com/Danube-Labs/javv-poc/issues/406) follow-up) ([#457](https://github.com/Danube-Labs/javv-poc/issues/457)) ([3c71b44](https://github.com/Danube-Labs/javv-poc/commit/3c71b44986af931ec58179065937120d32c1d747))
* **ui:** topbar user menu + m9 cap-logging parity ([#450](https://github.com/Danube-Labs/javv-poc/issues/450)) ([#451](https://github.com/Danube-Labs/javv-poc/issues/451)) ([94d2ae3](https://github.com/Danube-Labs/javv-poc/commit/94d2ae3cbca6981752d4a205d9aed6991e1e2dc4))


### Bug Fixes

* fleet-scoped events (auth, jobs, inspect) appear in the audit screen ([#458](https://github.com/Danube-Labs/javv-poc/issues/458)) ([e791625](https://github.com/Danube-Labs/javv-poc/commit/e791625e91057725ec0e6bfe70f03134c5475a18))

## [0.4.0](https://github.com/Danube-Labs/javv-poc/compare/v0.3.11...v0.4.0) (2026-07-17)


### Features

* **fe:** m9f slice 1: emptystate kit, zero-clusters cold start, testable nav gate ([#441](https://github.com/Danube-Labs/javv-poc/issues/441)) ([ea00e61](https://github.com/Danube-Labs/javv-poc/commit/ea00e61c3c30635ce6984912e7d10f2eaf6e12ce)), closes [#40](https://github.com/Danube-Labs/javv-poc/issues/40)
* **fe:** m9f slice 2: ⌘K command palette (global search + jump-to-screen) ([#443](https://github.com/Danube-Labs/javv-poc/issues/443)) ([2535009](https://github.com/Danube-Labs/javv-poc/commit/2535009eaf249c8dd9ad215674933b57f7b778a5))
* m9f slice 3: notification bell (poll, floating glass drawer, dismiss) + flat primary button ([#444](https://github.com/Danube-Labs/javv-poc/issues/444)) ([e60712c](https://github.com/Danube-Labs/javv-poc/commit/e60712cc402499a79074cfbc15ee4afdba00cc73))
* m9f slice 4: saved views v2, is/is-not filter negation, url-rewrite ownership fix ([#445](https://github.com/Danube-Labs/javv-poc/issues/445)) ([05287b9](https://github.com/Danube-Labs/javv-poc/commit/05287b99255e9f12b9683561b216863739616fe1))


### Bug Fixes

* **fe:** e2e paging spec polls the first grid query: skeleton rows race the cluster fetch ([#448](https://github.com/Danube-Labs/javv-poc/issues/448)) ([d9214f3](https://github.com/Danube-Labs/javv-poc/commit/d9214f3a097b6c28f088cb30db0ebca73ee7d392))


### Miscellaneous Chores

* cut the 0.4.0 minor release (m9f bolt) ([#449](https://github.com/Danube-Labs/javv-poc/issues/449)) ([f2f7cc7](https://github.com/Danube-Labs/javv-poc/commit/f2f7cc7a86769225027b4abaa5a351f490186a7d))

## [0.3.11](https://github.com/Danube-Labs/javv-poc/compare/v0.3.10...v0.3.11) (2026-07-17)


### Features

* **backend:** per-cluster findings-cleanup window: override doc + per-tenant sweep ([#437](https://github.com/Danube-Labs/javv-poc/issues/437)) ([c82a57e](https://github.com/Danube-Labs/javv-poc/commit/c82a57ee6495e111109252a8baf2a2e054f3a1fc)), closes [#431](https://github.com/Danube-Labs/javv-poc/issues/431)
* **fe:** cluster rides the url: global ?cluster= deep links (issue 433) ([#438](https://github.com/Danube-Labs/javv-poc/issues/438)) ([239b827](https://github.com/Danube-Labs/javv-poc/commit/239b82769a1a5ca3e3747ab4989e1f183100b12b)), closes [#433](https://github.com/Danube-Labs/javv-poc/issues/433)
* **ui:** cve detail refresh: wide layout, transposed evidence, kit cards ([#434](https://github.com/Danube-Labs/javv-poc/issues/434)) ([#439](https://github.com/Danube-Labs/javv-poc/issues/439)) ([ed584f9](https://github.com/Danube-Labs/javv-poc/commit/ed584f97b80db8b410bb50a47a9d08a5ad0ad3a2))
* **ui:** overview drops the duplicate scan-activity card for top-components + riskiest-images ([#426](https://github.com/Danube-Labs/javv-poc/issues/426)) ([f258a6d](https://github.com/Danube-Labs/javv-poc/commit/f258a6df1441dcf27067e2ba59c926a317b8a237))
* **ui:** section identity accents, scanner identity dots, slate table-head band ([#428](https://github.com/Danube-Labs/javv-poc/issues/428)) ([3aa68de](https://github.com/Danube-Labs/javv-poc/commit/3aa68decf41f680ba9fe3d415fc0127d5d68756f))


### Bug Fixes

* **fe:** clear grid rows on cluster/T switch: stale-tenant rows lingered under slow networks ([#436](https://github.com/Danube-Labs/javv-poc/issues/436)) ([a39863f](https://github.com/Danube-Labs/javv-poc/commit/a39863ffd6115fbb84a58e582f049ce3d7db37c5)), closes [#431](https://github.com/Danube-Labs/javv-poc/issues/431)

## [0.3.10](https://github.com/Danube-Labs/javv-poc/compare/v0.3.9...v0.3.10) (2026-07-16)


### Features

* **api:** team totals block on the contributors read ([#360](https://github.com/Danube-Labs/javv-poc/issues/360)) ([1096ef4](https://github.com/Danube-Labs/javv-poc/commit/1096ef4aa01258cd50a35fdb7a443d8ff5dbd5da))
* **backend:** approvals rail filters + facets on the queue endpoint (4b) ([#371](https://github.com/Danube-Labs/javv-poc/issues/371)) ([d82d81f](https://github.com/Danube-Labs/javv-poc/commit/d82d81f92391a11fe120a5a0371d7659ff6decb2)), closes [#38](https://github.com/Danube-Labs/javv-poc/issues/38)
* **backend:** sla_clock_at: the materialized d21 group clock (issue 363, pr 1/2) ([#365](https://github.com/Danube-Labs/javv-poc/issues/365)) ([1d92235](https://github.com/Danube-Labs/javv-poc/commit/1d92235374e3ccee1b37eee2e25073a0416033b8)), closes [#363](https://github.com/Danube-Labs/javv-poc/issues/363)
* **jobs:** findings long-window cleanup sweep: m9e slice 5, bolt wrap ([#412](https://github.com/Danube-Labs/javv-poc/issues/412)) ([fd47ed4](https://github.com/Danube-Labs/javv-poc/commit/fd47ed48f0c5291fc6334d5d60041aed75dff06c)), closes [#39](https://github.com/Danube-Labs/javv-poc/issues/39)
* **scanner:** namespace scope lists take fnmatch globs ([#409](https://github.com/Danube-Labs/javv-poc/issues/409)) ([fc7eba4](https://github.com/Danube-Labs/javv-poc/commit/fc7eba4f934dcbbbe125a46b8bc05ef9867afb5b)), closes [#39](https://github.com/Danube-Labs/javv-poc/issues/39)
* **ui:** approvals filter rail (m9d slice 4b, frontend) ([#372](https://github.com/Danube-Labs/javv-poc/issues/372)) ([a74b4bb](https://github.com/Danube-Labs/javv-poc/commit/a74b4bb57ce6952c471c91006ef76e09d205476b)), closes [#38](https://github.com/Danube-Labs/javv-poc/issues/38)
* **ui:** m9d slice 1: the audit log on the prototype table grammar ([#353](https://github.com/Danube-Labs/javv-poc/issues/353)) ([20b511c](https://github.com/Danube-Labs/javv-poc/commit/20b511ce088ddd0a34629f795d08e008270617c0))
* **ui:** m9d slice 2: scanner status on the shared data-screen grammar ([#356](https://github.com/Danube-Labs/javv-poc/issues/356)) ([e8c0529](https://github.com/Danube-Labs/javv-poc/commit/e8c0529570ebeb8ec3e47641ebc270804fe5bc3f))
* **ui:** m9d slice 3: contributors on the shared data-screen grammar ([#361](https://github.com/Danube-Labs/javv-poc/issues/361)) ([6f72897](https://github.com/Danube-Labs/javv-poc/commit/6f72897fc494157b7732536b365c2d8efb7cd608)), closes [#38](https://github.com/Danube-Labs/javv-poc/issues/38)
* **ui:** m9d slice 4: approvals review queue on the shared grammar ([#370](https://github.com/Danube-Labs/javv-poc/issues/370)) ([a1a66bb](https://github.com/Danube-Labs/javv-poc/commit/a1a66bb31d3898215ae47fbbbe9cf367cc27eae1)), closes [#38](https://github.com/Danube-Labs/javv-poc/issues/38)
* **ui:** m9e slice 1: settings shell + SLA policy panel ([#405](https://github.com/Danube-Labs/javv-poc/issues/405)) ([b8b672e](https://github.com/Danube-Labs/javv-poc/commit/b8b672e88d4e1fb983b18d15a04f386e4340b859))
* **ui:** m9e slice 2: tokens, users & roles, cluster panels ([#407](https://github.com/Danube-Labs/javv-poc/issues/407)) ([252675b](https://github.com/Danube-Labs/javv-poc/commit/252675b9b152263e64a7611b404d173d27edaab3))
* **ui:** m9e slice 3: scan-scope editor + scanning panel ([#408](https://github.com/Danube-Labs/javv-poc/issues/408)) ([3046502](https://github.com/Danube-Labs/javv-poc/commit/304650213d3e1b390a5f07f30452886e74454b1c))
* **ui:** m9e slice 4: data & opensearch panel + live freshness banner ([#411](https://github.com/Danube-Labs/javv-poc/issues/411)) ([dcd96bf](https://github.com/Danube-Labs/javv-poc/commit/dcd96bf554b2bdd4336595711b7bb5b567a182cb))
* **ui:** sla-breached attribute chip on the findings rail (issue 363, pr 2/2) ([#366](https://github.com/Danube-Labs/javv-poc/issues/366)) ([d6fb096](https://github.com/Danube-Labs/javv-poc/commit/d6fb0960753cba00e3627ef443b33eebe238cfc8)), closes [#363](https://github.com/Danube-Labs/javv-poc/issues/363)


### Bug Fixes

* **backend:** historical export reconstructs the cluster once (audit f-09) ([#397](https://github.com/Danube-Labs/javv-poc/issues/397)) ([fda2990](https://github.com/Danube-Labs/javv-poc/commit/fda29904df7d49b57c4019df4396da7417c5c9e5))
* **backend:** historical reads page to exhaustion, never a 10k cap (audit f-05/f-06) ([#392](https://github.com/Danube-Labs/javv-poc/issues/392)) ([8de360b](https://github.com/Danube-Labs/javv-poc/commit/8de360b178d1de35f837058bef7cc7fdf467643b))
* **backend:** jobs read to exhaustion: no 10k caps in rebuild/staleness ([#391](https://github.com/Danube-Labs/javv-poc/issues/391)) ([#396](https://github.com/Danube-Labs/javv-poc/issues/396)) ([863a6ab](https://github.com/Danube-Labs/javv-poc/commit/863a6abc63bfa47aff4ff3e7270b58ae269d8a95))
* **backend:** one id for a notification's _id and notification_id (audit f-03/f-13) ([#390](https://github.com/Danube-Labs/javv-poc/issues/390)) ([25aa1e8](https://github.com/Danube-Labs/javv-poc/commit/25aa1e89983354d75456d1335d8a864342f6bd60))
* **backend:** report status + download are owner-scoped (audit f-01/f-12) ([#388](https://github.com/Danube-Labs/javv-poc/issues/388)) ([d4a4238](https://github.com/Danube-Labs/javv-poc/commit/d4a4238b03550d1d774fd9aad91913b4a5b6ebd8))
* **ui:** export dialog carries the whole lens + past-t schedules (audit f-07/f-08/f-11) ([#393](https://github.com/Danube-Labs/javv-poc/issues/393)) ([100737a](https://github.com/Danube-Labs/javv-poc/commit/100737a2c860119faef403470274711a44cb33a6))
* **ui:** image csv export is an authenticated read, not admin-only (audit f-10) ([#395](https://github.com/Danube-Labs/javv-poc/issues/395)) ([7a93781](https://github.com/Danube-Labs/javv-poc/commit/7a93781572ad7f48e966c019813dad710d46705d))
* **ui:** lenses never flash the amber quiet claim before data lands ([#355](https://github.com/Danube-Labs/javv-poc/issues/355)) ([532f077](https://github.com/Danube-Labs/javv-poc/commit/532f077dc0fe21a9192e59f30b0ce8ce7e743128)), closes [#38](https://github.com/Danube-Labs/javv-poc/issues/38)
* **ui:** neutralize formula heads in the image csv export (audit f-02) ([#389](https://github.com/Danube-Labs/javv-poc/issues/389)) ([d0279f0](https://github.com/Danube-Labs/javv-poc/commit/d0279f037f2656cd804e604d3daff081f47882de))
* **ui:** rewound time chip names the viewed T from t itself ([#364](https://github.com/Danube-Labs/javv-poc/issues/364)) ([04dbc7d](https://github.com/Danube-Labs/javv-poc/commit/04dbc7d4e40e1b84168e4490eed07bd251c6acf0))
* **ui:** sla countdowns measure from the rewound t, never from today ([#362](https://github.com/Danube-Labs/javv-poc/issues/362)) ([a6acdc5](https://github.com/Danube-Labs/javv-poc/commit/a6acdc5bb5b4a8ac8550b3844042d1350ac4a944))

## [0.3.9](https://github.com/Danube-Labs/javv-poc/compare/v0.3.8...v0.3.9) (2026-07-11)


### Features

* **ui:** chip language A: derived hues, severity escalation, one depth treatment ([#350](https://github.com/Danube-Labs/javv-poc/issues/350)) ([229a728](https://github.com/Danube-Labs/javv-poc/commit/229a728728fdb733ce81cac128da9ad1f91b444b))
* **ui:** grid ergonomics: column drag-reorder on findings + images, cursor contract, first-seen column ([#348](https://github.com/Danube-Labs/javv-poc/issues/348)) ([a24e768](https://github.com/Danube-Labs/javv-poc/commit/a24e768c55d919d1f25714050f294e56ef494f09))


### Bug Fixes

* **api:** cap hourly trend buckets at a month of span ([#346](https://github.com/Danube-Labs/javv-poc/issues/346)) ([a562b1e](https://github.com/Danube-Labs/javv-poc/commit/a562b1e49d93b43b403bd324368a030e1e9b20d0)), closes [#343](https://github.com/Danube-Labs/javv-poc/issues/343)

## [0.3.8](https://github.com/Danube-Labs/javv-poc/compare/v0.3.7...v0.3.8) (2026-07-11)


### Features

* **api:** severity split on the findings trend ([#333](https://github.com/Danube-Labs/javv-poc/issues/333)) ([77801c6](https://github.com/Danube-Labs/javv-poc/commit/77801c6a0788e265a5bf9bc854d638c5554e3c48))
* **ui:** m9c slice 1: the overview dashboard ([#332](https://github.com/Danube-Labs/javv-poc/issues/332)) ([406dedf](https://github.com/Danube-Labs/javv-poc/commit/406dedf866da65acf720da33ffcd6d9c4892cc14)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)
* **ui:** M9c slice 2: the all-clusters fleet view ([#338](https://github.com/Danube-Labs/javv-poc/issues/338)) ([bcf7485](https://github.com/Danube-Labs/javv-poc/commit/bcf748510f02c41f4e019482cdfd5f15fe36f101))
* **ui:** M9c slice 3: running images + image detail on the committed inventory ([#339](https://github.com/Danube-Labs/javv-poc/issues/339)) ([4312607](https://github.com/Danube-Labs/javv-poc/commit/431260720b3ba48ed4587d91ad9e99fd840b4909))
* **ui:** overview 1b: severity lens, signal band, at-rest affordances ([#334](https://github.com/Danube-Labs/javv-poc/issues/334)) ([486e2ae](https://github.com/Danube-Labs/javv-poc/commit/486e2aef008e457ccf103f6137bee142773339c0)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)
* **ui:** scan-ingest lens above the findings + images tables ([#340](https://github.com/Danube-Labs/javv-poc/issues/340)) ([95eaa2f](https://github.com/Danube-Labs/javv-poc/commit/95eaa2fdc75ca96300574c6344df96824b273b7a)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)


### Bug Fixes

* **ui:** audit-343 wave: honest errors, restorable time range, semantics everywhere ([#344](https://github.com/Danube-Labs/javv-poc/issues/344)) ([19d3dfb](https://github.com/Danube-Labs/javv-poc/commit/19d3dfb7ec5cbc2d98845d82bbb2c96986bb52f3)), closes [#343](https://github.com/Danube-Labs/javv-poc/issues/343)
* **ui:** freshness banner: urgency treatment, 24h times, durations, 10-min poll ([#330](https://github.com/Danube-Labs/javv-poc/issues/330)) ([7e1c991](https://github.com/Danube-Labs/javv-poc/commit/7e1c9910a2ef0c0e293eeb091211d62ef269756a))
* **ui:** overview + findings polish: cursor, donut links, palette, note, column diet ([#335](https://github.com/Danube-Labs/javv-poc/issues/335)) ([ae706ce](https://github.com/Danube-Labs/javv-poc/commit/ae706ce686ef16a15208ab8a25a5023659be697f))
* **ui:** system-default cursor truly global: universal rule + ratchet ([#337](https://github.com/Danube-Labs/javv-poc/issues/337)) ([023f19b](https://github.com/Danube-Labs/javv-poc/commit/023f19b7c7f4336820cc9a19e7463a9bc8f23b32)), closes [#37](https://github.com/Danube-Labs/javv-poc/issues/37)

## [0.3.7](https://github.com/Danube-Labs/javv-poc/compare/v0.3.6...v0.3.7) (2026-07-10)


### Features

* **ui:** collapsible icon-rail sidebar (226px ↔ 64px, Nuxt UI grammar) ([#320](https://github.com/Danube-Labs/javv-poc/issues/320)) ([cff81a3](https://github.com/Danube-Labs/javv-poc/commit/cff81a384d9250f40f89c7010566b822abdbe2a3)), closes [#319](https://github.com/Danube-Labs/javv-poc/issues/319)
* **ui:** motion layer: open/close transitions baked into the kit ([#323](https://github.com/Danube-Labs/javv-poc/issues/323)) ([fcd1552](https://github.com/Danube-Labs/javv-poc/commit/fcd155226a99ff61b7764d8f191377d7f1d90cc6))
* **ui:** toast notifications: the app-wide confirmation channel ([#324](https://github.com/Danube-Labs/javv-poc/issues/324)) ([8bfed97](https://github.com/Danube-Labs/javv-poc/commit/8bfed97921b1794a12379d152b36129ddbf82ad9)), closes [#319](https://github.com/Danube-Labs/javv-poc/issues/319)


### Bug Fixes

* **audit:** activity feed updates without a page reload ([#321](https://github.com/Danube-Labs/javv-poc/issues/321)) ([ee51640](https://github.com/Danube-Labs/javv-poc/commit/ee51640092123e72422705c0a0c136a78bb6bb78))

## [0.3.6](https://github.com/Danube-Labs/javv-poc/compare/v0.3.5...v0.3.6) (2026-07-10)


### Features

* **dx:** agent design contract, style ratchet, /visual-test + /qa commands ([#285](https://github.com/Danube-Labs/javv-poc/issues/285)) ([f8b2cfb](https://github.com/Danube-Labs/javv-poc/commit/f8b2cfbd0bc4fab9d01fdc5d104a9dbf1990dbec)), closes [#284](https://github.com/Danube-Labs/javv-poc/issues/284)
* **m9a:** app shell, login + must_change, banners, global time picker (slice 3) ([#289](https://github.com/Danube-Labs/javv-poc/issues/289)) ([8c915ad](https://github.com/Danube-Labs/javv-poc/commit/8c915ad35ce9b3473ad2b45f6bdb12af71766c1c))
* **m9a:** frontend scaffold, design tokens, style gates, fe logger (slice 1) ([#287](https://github.com/Danube-Labs/javv-poc/issues/287)) ([59f6428](https://github.com/Danube-Labs/javv-poc/commit/59f642823ccd6c66c28fa8a0688e306e658fd765))
* **m9a:** reusable filter module: one fields config drives rail + bar (slice 4) ([#290](https://github.com/Danube-Labs/javv-poc/issues/290)) ([bfb3a95](https://github.com/Danube-Labs/javv-poc/commit/bfb3a9501e18d2f40b2436e106eeafb2ef92104a))
* **m9a:** typed api client + i4/i7 contract gate (slice 2) ([#288](https://github.com/Danube-Labs/javv-poc/issues/288)) ([55e70ac](https://github.com/Danube-Labs/javv-poc/commit/55e70ac73aff21d9a9b2de80f6e927c0b662bb4c)), closes [#35](https://github.com/Danube-Labs/javv-poc/issues/35)
* **m9b:** bulk triage, export dialog, metadata pack: slice 4 (bolt wrap) ([#309](https://github.com/Danube-Labs/javv-poc/issues/309)) ([e115d18](https://github.com/Danube-Labs/javv-poc/commit/e115d18d3b730d6b2ba8f4e0fc80b4773abab601))
* **m9b:** finding detail screen: per-scanner evidence, images affected, cve-click navigation (slice 2) ([#304](https://github.com/Danube-Labs/javv-poc/issues/304)) ([c4eb6f0](https://github.com/Danube-Labs/javv-poc/commit/c4eb6f0fc5a3ce1cf0b2f55f12c6d17b8dec6ea8))
* **m9b:** shared chip set + lazy findings grid (slice 1) ([#292](https://github.com/Danube-Labs/javv-poc/issues/292)) ([ed40437](https://github.com/Danube-Labs/javv-poc/commit/ed404379c39d109aebc9a528e067ecefb9f94ed2))
* **m9b:** triage panel: 6-state vex, risk-accept dialog, decisions card (slice 3) ([#305](https://github.com/Danube-Labs/javv-poc/issues/305)) ([0af963f](https://github.com/Danube-Labs/javv-poc/commit/0af963f773d332777e27b708e675b9fdc78f0a4b))
* prototype-fidelity time picker + columns menu on the findings grid ([#297](https://github.com/Danube-Labs/javv-poc/issues/297)) ([aeb92ec](https://github.com/Danube-Labs/javv-poc/commit/aeb92ec596582391ad646e30a021f41659c7f767)), closes [#296](https://github.com/Danube-Labs/javv-poc/issues/296)
* switch ui font to hanken grotesk (operator a/b ruling) ([#295](https://github.com/Danube-Labs/javv-poc/issues/295)) ([eb89282](https://github.com/Danube-Labs/javv-poc/commit/eb89282dc905fefa97f439c78b9ad63b9600f138))
* **ui:** interaction feedback + spacing rhythm + surface elevation pass ([#307](https://github.com/Danube-Labs/javv-poc/issues/307)) ([9b81c83](https://github.com/Danube-Labs/javv-poc/commit/9b81c830ebaa9beabacd20b4ed25979a93c83340))


### Bug Fixes

* **m9b:** as_of reader rejects q explicitly; parity guard against ignored filters ([#310](https://github.com/Danube-Labs/javv-poc/issues/310)) ([f6c5936](https://github.com/Danube-Labs/javv-poc/commit/f6c5936ba8b76af3e3bd35d7f5803d7bd511d86c))
* **ui:** visible hover feedback on every control + unclipped segmented bars ([#314](https://github.com/Danube-Labs/javv-poc/issues/314)) ([662c00c](https://github.com/Danube-Labs/javv-poc/commit/662c00c528934635895abf2c6c509aa8b53757e7))
* wcag aa contrast for hint text, dark-chrome labels and teal text ([#294](https://github.com/Danube-Labs/javv-poc/issues/294)) ([5aee72b](https://github.com/Danube-Labs/javv-poc/commit/5aee72beabbba44bdd095d340dcf671b84256f39))

## [0.3.5](https://github.com/Danube-Labs/javv-poc/compare/v0.3.4...v0.3.5) (2026-07-08)


### Features

* **274:** full-word canonical severity: severity_canonical query key + sla fix (slice 1) ([#277](https://github.com/Danube-Labs/javv-poc/issues/277)) ([5a74dc8](https://github.com/Danube-Labs/javv-poc/commit/5a74dc85074d1ca2f9293a5dee677c1bcd7030a6)), closes [#274](https://github.com/Danube-Labs/javv-poc/issues/274)
* **274:** scanner full-word severities + count-column shim, smoke vocabulary pin (slice 2) ([#278](https://github.com/Danube-Labs/javv-poc/issues/278)) ([7c8ffb8](https://github.com/Danube-Labs/javv-poc/commit/7c8ffb8bd2f252267343f024e4e4dccbdd5c7bb9)), closes [#274](https://github.com/Danube-Labs/javv-poc/issues/274)
* **m8e:** system-views store + create/list: the saved-views foundation (slice 1) ([#273](https://github.com/Danube-Labs/javv-poc/issues/273)) ([050b23a](https://github.com/Danube-Labs/javv-poc/commit/050b23ade6afd2e4aa6650eb157190528978716a)), closes [#242](https://github.com/Danube-Labs/javv-poc/issues/242)
* **m8e:** views mutations: owner-or-admin, cas, and the deep-link round-trip (slice 2) ([#276](https://github.com/Danube-Labs/javv-poc/issues/276)) ([b7e80da](https://github.com/Danube-Labs/javv-poc/commit/b7e80dacf39b53e934f585dc42ba575fd7305198)), closes [#242](https://github.com/Danube-Labs/javv-poc/issues/242)


### Bug Fixes

* **trends:** absolute window bounds: kill the createWeight now-datemath ci flake ([#279](https://github.com/Danube-Labs/javv-poc/issues/279)) ([fd81951](https://github.com/Danube-Labs/javv-poc/commit/fd81951dd9ccbd74fea691c7e641e9443576455e))

## [0.3.4](https://github.com/Danube-Labs/javv-poc/compare/v0.3.3...v0.3.4) (2026-07-08)


### Features

* **m8c:** audit read + catalog-first scanner provenance (slice 1) ([#267](https://github.com/Danube-Labs/javv-poc/issues/267)) ([b5d322b](https://github.com/Danube-Labs/javv-poc/commit/b5d322b8fe53e745c9c675af385a50a9df459c1e)), closes [#240](https://github.com/Danube-Labs/javv-poc/issues/240)
* **m8c:** running-images read + cluster registry: the m9-prep reads close (slice 2) ([#269](https://github.com/Danube-Labs/javv-poc/issues/269)) ([#270](https://github.com/Danube-Labs/javv-poc/issues/270)) ([73ef41b](https://github.com/Danube-Labs/javv-poc/commit/73ef41b7deef44c23ce88a5bddc42de44609f8be)), closes [#240](https://github.com/Danube-Labs/javv-poc/issues/240)
* **m8d:** ptype through every read surface: filter, facets, groups, as-of-t (slice 2) ([#272](https://github.com/Danube-Labs/javv-poc/issues/272)) ([dea5136](https://github.com/Danube-Labs/javv-poc/commit/dea5136bb51d47527c1490142618cdafe635ff30)), closes [#241](https://github.com/Danube-Labs/javv-poc/issues/241)
* **m8d:** ptype through the write path: envelope v4 with a v3 acceptance window (slice 1) ([#271](https://github.com/Danube-Labs/javv-poc/issues/271)) ([9ee1fea](https://github.com/Danube-Labs/javv-poc/commit/9ee1fea89287d5152b423dbe92e3977bc5505b40)), closes [#241](https://github.com/Danube-Labs/javv-poc/issues/241)

## [0.3.3](https://github.com/Danube-Labs/javv-poc/compare/v0.3.2...v0.3.3) (2026-07-07)


### Features

* **m8a:** inventory commit manifest + cycle-end certification (slice 2) ([#256](https://github.com/Danube-Labs/javv-poc/issues/256)) ([1ace495](https://github.com/Danube-Labs/javv-poc/commit/1ace495a1867006a5f38b253d5beecf60bf58292)), closes [#33](https://github.com/Danube-Labs/javv-poc/issues/33)
* **m8a:** per-scan occurrence snapshots appended in the d39 spine (slice 1) ([#254](https://github.com/Danube-Labs/javv-poc/issues/254)) ([c2b16df](https://github.com/Danube-Labs/javv-poc/commit/c2b16dfc1ceba6eeba6373198a711966defb7781)), closes [#33](https://github.com/Danube-Labs/javv-poc/issues/33)
* **m8a:** rebuild-state scanner-presence arm + exact self-heal floor (slice 3) ([#258](https://github.com/Danube-Labs/javv-poc/issues/258)) ([c27f36f](https://github.com/Danube-Labs/javv-poc/commit/c27f36f6bd70619e14db24cebd8badd6d7e1b731))
* **m8b:** audit replay + decisions-active-at-t: the human dimension (slice 2) ([#264](https://github.com/Danube-Labs/javv-poc/issues/264)) ([2a091ee](https://github.com/Danube-Labs/javv-poc/commit/2a091eea9a75400035fac6caffe510e126d327a3))
* **m8b:** r-catalog point-in-time primitives (slice 1) ([#263](https://github.com/Danube-Labs/javv-poc/issues/263)) ([36670d7](https://github.com/Danube-Labs/javv-poc/commit/36670d742f38e95af3cebbefc056605463d4d7ab)), closes [#34](https://github.com/Danube-Labs/javv-poc/issues/34)
* **m8b:** the as-of-t reader: findings page/facets/groups reconstructed (slice 3) ([#265](https://github.com/Danube-Labs/javv-poc/issues/265)) ([29f735a](https://github.com/Danube-Labs/javv-poc/commit/29f735a94e5afbc789c11e6150bc0c0c95e54d6f)), closes [#34](https://github.com/Danube-Labs/javv-poc/issues/34)
* **m8b:** trends + contributors at t, reader registration, export unpark (slice 4) ([#266](https://github.com/Danube-Labs/javv-poc/issues/266)) ([da961e8](https://github.com/Danube-Labs/javv-poc/commit/da961e88b651ce02e8a7a98c50b6c66f10e9ad19))


### Bug Fixes

* **ci:** allow fs.read=.. in the scanner-images bake: buildx runner drift enforces entitlements ([#260](https://github.com/Danube-Labs/javv-poc/issues/260)) ([7e2a0ec](https://github.com/Danube-Labs/javv-poc/commit/7e2a0ec53caca24e84b0cfb6bafba3731128a98f))

## [0.3.2](https://github.com/Danube-Labs/javv-poc/compare/v0.3.1...v0.3.2) (2026-07-07)


### Features

* **m7:** bulk_triage report kind: capability-gated, frozen at enqueue (slice 5) ([#252](https://github.com/Danube-Labs/javv-poc/issues/252)) ([6c4c442](https://github.com/Danube-Labs/javv-poc/commit/6c4c44227cf71d5bf0f41c7eeb7d79e8e562c907)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)
* **m7:** drain worker, chunked results, signed download, notifications bell (slice 3) ([#248](https://github.com/Danube-Labs/javv-poc/issues/248)) ([83ca734](https://github.com/Danube-Labs/javv-poc/commit/83ca73491be849d5528e41472c8224b4d13254f0)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)
* **m7:** occ claim + fenced lease for the report queue (slice 2) ([#246](https://github.com/Danube-Labs/javv-poc/issues/246)) ([8a7d71b](https://github.com/Danube-Labs/javv-poc/commit/8a7d71b36b9f0ce82fcf09a17713eb4c3663bf28)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)
* **m7:** ttl + orphan sweep for the report queue (slice 4) ([#251](https://github.com/Danube-Labs/javv-poc/issues/251)) ([b7b99d7](https://github.com/Danube-Labs/javv-poc/commit/b7b99d7b53b1fddef3f6249fd28b928765be5b93)), closes [#32](https://github.com/Danube-Labs/javv-poc/issues/32)


### Bug Fixes

* **ci:** serialize the store-exclusive admin demote race: it 401'd concurrent tests ([#250](https://github.com/Danube-Labs/javv-poc/issues/250)) ([49ce86a](https://github.com/Danube-Labs/javv-poc/commit/49ce86ae255fca9b0998b9aacb2815cf4c306bbf)), closes [#245](https://github.com/Danube-Labs/javv-poc/issues/245)

## [0.3.1](https://github.com/Danube-Labs/javv-poc/compare/v0.3.0...v0.3.1) (2026-07-07)


### Features

* expand /metrics: request histogram, os health, cas churn, limits, auth (audit [#220](https://github.com/Danube-Labs/javv-poc/issues/220)) ([#229](https://github.com/Danube-Labs/javv-poc/issues/229)) ([101c009](https://github.com/Danube-Labs/javv-poc/commit/101c009848c076397a82ea6d1b560f787c19b04a)), closes [#66](https://github.com/Danube-Labs/javv-poc/issues/66)
* **m6:** scanner-freshness read: get /api/v1/scanners/freshness (audit d-1, [#218](https://github.com/Danube-Labs/javv-poc/issues/218)) ([#227](https://github.com/Danube-Labs/javv-poc/issues/227)) ([1aab7a1](https://github.com/Danube-Labs/javv-poc/commit/1aab7a1476f71f7b4958962c33887a4dc991366c)), closes [#35](https://github.com/Danube-Labs/javv-poc/issues/35)
* **m7:** scheduled-export queue foundation: indexes + enqueue endpoint (slice 1, [#32](https://github.com/Danube-Labs/javv-poc/issues/32)) ([#213](https://github.com/Danube-Labs/javv-poc/issues/213)) ([a5d714d](https://github.com/Danube-Labs/javv-poc/commit/a5d714d0d010a8b0d4cdd5fca7e4368640b8dffb))
* validate settings at boot: borked config crash-loops readably (audit [#219](https://github.com/Danube-Labs/javv-poc/issues/219)) ([#228](https://github.com/Danube-Labs/javv-poc/issues/228)) ([f0a44e4](https://github.com/Danube-Labs/javv-poc/commit/f0a44e4a28cab6fb3b237d7ca723c16334fc6816)), closes [#66](https://github.com/Danube-Labs/javv-poc/issues/66)

## [0.3.0](https://github.com/Danube-Labs/javv-poc/compare/v0.2.16...v0.3.0) (2026-07-06)


### Features

* **m5c:** warn when reproject drains a conflict storm (audit [#186](https://github.com/Danube-Labs/javv-poc/issues/186) nicety) ([#201](https://github.com/Danube-Labs/javv-poc/issues/201)) ([ae0c17e](https://github.com/Danube-Labs/javv-poc/commit/ae0c17e1aadbc1b80f18bdabf22dd9f481a7057e))


### Bug Fixes

* **m5c:** journal-first audit completeness on new write paths + last-admin race (audit [#188](https://github.com/Danube-Labs/javv-poc/issues/188)) ([#204](https://github.com/Danube-Labs/javv-poc/issues/204)) ([cba3987](https://github.com/Danube-Labs/javv-poc/commit/cba3987cc4027760341bd6baccc98df604e37ebd))
* **m5c:** reproject_cve guarded RMW: drain conflicts, re-check ownership (audit [#186](https://github.com/Danube-Labs/javv-poc/issues/186)) ([#197](https://github.com/Danube-Labs/javv-poc/issues/197)) ([87bf402](https://github.com/Danube-Labs/javv-poc/commit/87bf4028f7d378a28845e0ec60dd377e16c60bc3))
* **m5d:** exact paged-composite group clock, no sibling truncation (audit [#187](https://github.com/Danube-Labs/javv-poc/issues/187)) ([#200](https://github.com/Danube-Labs/javv-poc/issues/200)) ([dc1c728](https://github.com/Danube-Labs/javv-poc/commit/dc1c728577b924d433c55622e9199c04b13fb3f6))
* **m6:** bound export/read-path DoS: bulk sync + export/PIT caps (audit [#189](https://github.com/Danube-Labs/javv-poc/issues/189)) ([#206](https://github.com/Danube-Labs/javv-poc/issues/206)) ([7ac2ff1](https://github.com/Danube-Labs/javv-poc/commit/7ac2ff1e73cc379c9ed4fab50f56d6fdfb40e722))
* **m6:** contributors: count decision rows + page handling rows (audit [#190](https://github.com/Danube-Labs/javv-poc/issues/190)) ([#207](https://github.com/Danube-Labs/javv-poc/issues/207)) ([582125f](https://github.com/Danube-Labs/javv-poc/commit/582125fc3a1f845b603b054b2e861867c93aac4f))
* **m6:** hardening & hygiene batch: reserved usernames, redaction, purl, docs (audit [#192](https://github.com/Danube-Labs/javv-poc/issues/192)) ([#210](https://github.com/Danube-Labs/javv-poc/issues/210)) ([048687f](https://github.com/Danube-Labs/javv-poc/commit/048687f4480ed713d9b3664c03f5bd9f748068e2))
* **m6:** read-path robustness: cursor errors 4xx + drop read-side refresh (audit [#191](https://github.com/Danube-Labs/javv-poc/issues/191)) ([#209](https://github.com/Danube-Labs/javv-poc/issues/209)) ([1cfe3ee](https://github.com/Danube-Labs/javv-poc/commit/1cfe3ee5fba3fddddd424160449fe01ee8223e89))


### Miscellaneous Chores

* cut the 0.3.0 minor release (audit wave) ([#211](https://github.com/Danube-Labs/javv-poc/issues/211)) ([c8d3251](https://github.com/Danube-Labs/javv-poc/commit/c8d325141d7244313befd13190c6d835c5f3deaa))

## [0.2.16](https://github.com/Danube-Labs/javv-poc/compare/v0.2.15...v0.2.16) (2026-07-06)


### Bug Fixes

* **m5c/m6:** validate triage + decision vocabularies (audit [#185](https://github.com/Danube-Labs/javv-poc/issues/185)) ([#195](https://github.com/Danube-Labs/javv-poc/issues/195)) ([b371923](https://github.com/Danube-Labs/javv-poc/commit/b3719238311cc34bdd067424be287b29f1408b17))

## [0.2.15](https://github.com/Danube-Labs/javv-poc/compare/v0.2.14...v0.2.15) (2026-07-05)


### Features

* **m6:** csv + vex export and the as-of-t dispatcher seam (slices 5-7) ([#181](https://github.com/Danube-Labs/javv-poc/issues/181)) ([f8393fa](https://github.com/Danube-Labs/javv-poc/commit/f8393fa8c213f96bcb88cbe574b8080a5f18e7a5))

## [0.2.14](https://github.com/Danube-Labs/javv-poc/compare/v0.2.13...v0.2.14) (2026-07-05)


### Features

* **logging:** structured per-request line: method/path/status/duration_ms fields ([#178](https://github.com/Danube-Labs/javv-poc/issues/178)) ([215b684](https://github.com/Danube-Labs/javv-poc/commit/215b684326ab4c37e200922548ff8c5d4c1cf374)), closes [#156](https://github.com/Danube-Labs/javv-poc/issues/156)
* **m6:** contributors: audit-log leaderboard, ttr, sla-hit % (slice 4) ([#177](https://github.com/Danube-Labs/javv-poc/issues/177)) ([70c6824](https://github.com/Danube-Labs/javv-poc/commit/70c6824e2da40a29efe272985878e58683cf29d2)), closes [#31](https://github.com/Danube-Labs/javv-poc/issues/31)

## [0.2.13](https://github.com/Danube-Labs/javv-poc/compare/v0.2.12...v0.2.13) (2026-07-05)


### Features

* **m6:** trends: committed scans by cardinality(commit_key) + new/resolved series (slice 3) ([#175](https://github.com/Danube-Labs/javv-poc/issues/175)) ([231eb34](https://github.com/Danube-Labs/javv-poc/commit/231eb343f6b6b9f8162a94b2fc11cb99b494cf14)), closes [#31](https://github.com/Danube-Labs/javv-poc/issues/31)

## [0.2.12](https://github.com/Danube-Labs/javv-poc/compare/v0.2.11...v0.2.12) (2026-07-05)


### Features

* **m6:** faceted findings search: PIT cursor paging + overdue decoration (slice 1) ([#170](https://github.com/Danube-Labs/javv-poc/issues/170)) ([c3ea427](https://github.com/Danube-Labs/javv-poc/commit/c3ea4275e0c9177f6c927f1c17076e609334babc)), closes [#31](https://github.com/Danube-Labs/javv-poc/issues/31)
* **m6:** scanner-faceted aggregations + composite group paging (slice 2) ([#172](https://github.com/Danube-Labs/javv-poc/issues/172)) ([cf2793c](https://github.com/Danube-Labs/javv-poc/commit/cf2793c0418ed3c3b24419e4e1cb82ef97394a1a))

## [0.2.11](https://github.com/Danube-Labs/javv-poc/compare/v0.2.10...v0.2.11) (2026-07-05)


### Bug Fixes

* **m6:** ingest stamp conflict 500 + the [#117](https://github.com/Danube-Labs/javv-poc/issues/117) refresh measurement bench ([#168](https://github.com/Danube-Labs/javv-poc/issues/168)) ([9b0d75e](https://github.com/Danube-Labs/javv-poc/commit/9b0d75ef4ed19bfafb86a924d56b7add39c40b14))

## [0.2.10](https://github.com/Danube-Labs/javv-poc/compare/v0.2.9...v0.2.10) (2026-07-05)


### Features

* **m5d:** SLA/overdue + bulk triage + risk-accept approval list ([#165](https://github.com/Danube-Labs/javv-poc/issues/165)) ([0f30705](https://github.com/Danube-Labs/javv-poc/commit/0f3070525df9188fd6540a0ec2fdeba0f9d548b1))

## [0.2.9](https://github.com/Danube-Labs/javv-poc/compare/v0.2.8...v0.2.9) (2026-07-05)


### Features

* **m5c:** decisions & projection: precedence ladder, D22 gate, reproject triggers, rebuild-state ([#163](https://github.com/Danube-Labs/javv-poc/issues/163)) ([f3bb822](https://github.com/Danube-Labs/javv-poc/commit/f3bb822acee8fed010f57c0ea2cd371c1d35a4a2))

## [0.2.8](https://github.com/Danube-Labs/javv-poc/compare/v0.2.7...v0.2.8) (2026-07-05)


### Features

* **observability:** shared logging lib, log levels, OpenSearch touch visibility ([#159](https://github.com/Danube-Labs/javv-poc/issues/159)) ([cdb1fce](https://github.com/Danube-Labs/javv-poc/commit/cdb1fce3f32583542417e21e0f3231db21e5e42d))

## [0.2.7](https://github.com/Danube-Labs/javv-poc/compare/v0.2.6...v0.2.7) (2026-07-05)


### Features

* **audit:** task d - admin user/role management (fr-18) ([#151](https://github.com/Danube-Labs/javv-poc/issues/151)) ([7b0a8ea](https://github.com/Danube-Labs/javv-poc/commit/7b0a8ea42551e7ca5e73c237bfb758909ab5a040)), closes [#141](https://github.com/Danube-Labs/javv-poc/issues/141)


### Bug Fixes

* **audit:** task a - triage/audit correctness (m-1, m-2, m-3) ([#148](https://github.com/Danube-Labs/javv-poc/issues/148)) ([960e117](https://github.com/Danube-Labs/javv-poc/commit/960e1171224fc9f29696fe458837aea56b19e413)), closes [#138](https://github.com/Danube-Labs/javv-poc/issues/138)
* **audit:** task c - auth hardening bundle ([#152](https://github.com/Danube-Labs/javv-poc/issues/152)) ([2ac20d6](https://github.com/Danube-Labs/javv-poc/commit/2ac20d607c573dd52cfd9f719def365ef7335b77)), closes [#140](https://github.com/Danube-Labs/javv-poc/issues/140)
* **audit:** task e - token admin polish ([#153](https://github.com/Danube-Labs/javv-poc/issues/153)) ([5b72c2c](https://github.com/Danube-Labs/javv-poc/commit/5b72c2cca64805ff46e3b100dee64f67477fb680)), closes [#142](https://github.com/Danube-Labs/javv-poc/issues/142)
* **audit:** task f - lifecycle/jobs robustness ([#154](https://github.com/Danube-Labs/javv-poc/issues/154)) ([4fa71a1](https://github.com/Danube-Labs/javv-poc/commit/4fa71a1c50990eacdc17182bd218c1a8bade8609)), closes [#143](https://github.com/Danube-Labs/javv-poc/issues/143)

## [0.2.6](https://github.com/Danube-Labs/javv-poc/compare/v0.2.5...v0.2.6) (2026-07-04)


### Features

* **m5b:** FR-7 state machine + the structured audit writer (slices 1–2) ([#133](https://github.com/Danube-Labs/javv-poc/issues/133)) ([6f56ca7](https://github.com/Danube-Labs/javv-poc/commit/6f56ca7d294046edeae078fd9145a031b068c4c4))
* **m5b:** triage service/route + decision lifecycle (slices 3–4) ([#136](https://github.com/Danube-Labs/javv-poc/issues/136)) ([6b8516d](https://github.com/Danube-Labs/javv-poc/commit/6b8516d7340fb080ebb03433a5b8b2167ceb0088))

## [0.2.5](https://github.com/Danube-Labs/javv-poc/compare/v0.2.4...v0.2.5) (2026-07-04)


### Features

* **m5a:** auth foundation: argon2id passwords + server-side sessions (slices 1–2) ([#127](https://github.com/Danube-Labs/javv-poc/issues/127)) ([dc0f79b](https://github.com/Danube-Labs/javv-poc/commit/dc0f79b5b312d30d65eabe016d0be37d3ea71afb))
* **m5a:** login/logout + lockout + bootstrap admin + capability RBAC (slices 3–4) ([#129](https://github.com/Danube-Labs/javv-poc/issues/129)) ([8334ceb](https://github.com/Danube-Labs/javv-poc/commit/8334ceb5593cbcfc7c9a0b59832be6fa0d50e190))
* **m5a:** tenant chokepoint + standing RBAC/IDOR suite + token admin + auth auditing (slices 5–6) ([#130](https://github.com/Danube-Labs/javv-poc/issues/130)) ([8a54f94](https://github.com/Danube-Labs/javv-poc/commit/8a54f94c689413f285a0f868e103ff58eea67f53))

## [0.2.4](https://github.com/Danube-Labs/javv-poc/compare/v0.2.3...v0.2.4) (2026-07-04)


### Features

* **m4:** scanner-disagreement flags: severity + count pair (D5a/D5b, slice 3) ([#124](https://github.com/Danube-Labs/javv-poc/issues/124)) ([6dbdf7d](https://github.com/Danube-Labs/javv-poc/commit/6dbdf7d392ca4a52505c1f9ad2e2588980c650a7)), closes [#26](https://github.com/Danube-Labs/javv-poc/issues/26)
* **m4:** write aliases + lifecycle sweep: rollover & per-cluster retention (slices 1–2) ([#122](https://github.com/Danube-Labs/javv-poc/issues/122)) ([4631eca](https://github.com/Danube-Labs/javv-poc/commit/4631eca8a2774fe3306204c0942f2d34f85c17ab))

## [0.2.3](https://github.com/Danube-Labs/javv-poc/compare/v0.2.2...v0.2.3) (2026-07-03)


### Features

* **m3:** backend-allocated scan_order: D45, slice 1 of M3 ([#103](https://github.com/Danube-Labs/javv-poc/issues/103)) ([8719ac6](https://github.com/Danube-Labs/javv-poc/commit/8719ac62a4b36e0fd1e201dacc44abaf4987b8c2)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** partial-doc merge: human triage survives rescans (D31, slice 2) ([#105](https://github.com/Danube-Labs/javv-poc/issues/105)) ([0080150](https://github.com/Danube-Labs/javv-poc/commit/00801503b3e030309834aa394aa26f6f0fc6223d)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** per-digest watermark CAS: the create+update guard (D40, slice 3) ([#106](https://github.com/Danube-Labs/javv-poc/issues/106)) ([f5e217e](https://github.com/Danube-Labs/javv-poc/commit/f5e217e76d79ddb4de30d0f167a7ff5ef293b08d)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** reconcile-on-commit: resolved CVEs leave the now grid (D37/D38, slice 5) ([#107](https://github.com/Danube-Labs/javv-poc/issues/107)) ([a4e4bd5](https://github.com/Danube-Labs/javv-poc/commit/a4e4bd56d13e4859d5bb58adf326ab63b47bb686)), closes [#25](https://github.com/Danube-Labs/javv-poc/issues/25)
* **m3:** two-timer staleness sweep: flag data the scanner stopped refreshing (D20, slice 6) ([#108](https://github.com/Danube-Labs/javv-poc/issues/108)) ([8972f2e](https://github.com/Danube-Labs/javv-poc/commit/8972f2ef8e67b614182effa1a499255c8c70ce66))


### Bug Fixes

* **m3:** audit follow-ups (M-1/M-4, m-1/m-3/m-4/m-5/m-7) ([#119](https://github.com/Danube-Labs/javv-poc/issues/119)) ([299a56f](https://github.com/Danube-Labs/javv-poc/commit/299a56fb59c155bfd7f7f46ab6d9aa7bb2e5f552))

## [0.2.2](https://github.com/Danube-Labs/javv-poc/compare/v0.2.1...v0.2.2) (2026-07-02)


### Features

* stamp effective_config on the envelope: schema v3 (D44/FR-25) ([#101](https://github.com/Danube-Labs/javv-poc/issues/101)) ([9f8331c](https://github.com/Danube-Labs/javv-poc/commit/9f8331cc544d1fc19e58de66f15d0288664408f8)), closes [#91](https://github.com/Danube-Labs/javv-poc/issues/91)


### Bug Fixes

* **scanner:** stamp trivy vuln-DB provenance via a per-cycle version call ([#99](https://github.com/Danube-Labs/javv-poc/issues/99)) ([5affa4a](https://github.com/Danube-Labs/javv-poc/commit/5affa4a8fa01433011482c7a6d1c90db341172f4)), closes [#96](https://github.com/Danube-Labs/javv-poc/issues/96)

## [0.2.1](https://github.com/Danube-Labs/javv-poc/compare/v0.2.0...v0.2.1) (2026-07-02)


### Features

* M2 snapshot/restore: durability early ([#88](https://github.com/Danube-Labs/javv-poc/issues/88)) ([cd110fe](https://github.com/Danube-Labs/javv-poc/commit/cd110fefce7e4671d3915af5113582a7e4a7534e))
* **scanner:** env-configurable Trivy/Grype scan flags ([#91](https://github.com/Danube-Labs/javv-poc/issues/91) phase 1) ([#92](https://github.com/Danube-Labs/javv-poc/issues/92)) ([fa65374](https://github.com/Danube-Labs/javv-poc/commit/fa653746a353112808e7c953ab11dead54e6df4e))
* UI-configurable scan scope via system-config ([#94](https://github.com/Danube-Labs/javv-poc/issues/94), D43/FR-24) ([#95](https://github.com/Danube-Labs/javv-poc/issues/95)) ([8c26032](https://github.com/Danube-Labs/javv-poc/commit/8c26032b43847c43c74e119649231161e37e1140))

## [0.2.0](https://github.com/Danube-Labs/javv-poc/compare/v0.1.2...v0.2.0) (2026-07-02)


### Features

* **backend:** hardened ingest endpoint + full-envelope contract (M1 slice 3) ([#83](https://github.com/Danube-Labs/javv-poc/issues/83)) ([a5d9a5d](https://github.com/Danube-Labs/javv-poc/commit/a5d9a5d988503608e99f1f530163fd33a6ca5da0)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)
* **backend:** M1 skeleton: app factory, lifespan, health, error envelope ([#76](https://github.com/Danube-Labs/javv-poc/issues/76)) ([4b1eb04](https://github.com/Danube-Labs/javv-poc/commit/4b1eb045b2ad633d6c8cd6048b91010a9ac3e9fa)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)
* **backend:** observability + CI OpenSearch service: M1 complete ([#85](https://github.com/Danube-Labs/javv-poc/issues/85)) ([b97ffcf](https://github.com/Danube-Labs/javv-poc/commit/b97ffcfd5221010beecb1316dd5d2fe841b1162d)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)
* **backend:** versioned index bootstrap (M1 slice 2) ([#82](https://github.com/Danube-Labs/javv-poc/issues/82)) ([ab15c79](https://github.com/Danube-Labs/javv-poc/commit/ab15c7976abced99fb9669e42c407dbd65b7601b))
* wire scanner auth to the ingest endpoint + token-mint CLI (e2e proven) ([#84](https://github.com/Danube-Labs/javv-poc/issues/84)) ([97ad07c](https://github.com/Danube-Labs/javv-poc/commit/97ad07cad9ea529536f371a8164b5b633228cd72))

## [0.1.2](https://github.com/Danube-Labs/javv-poc/compare/v0.1.1...v0.1.2) (2026-07-01)


### Features

* **scanner:** stamp observed topology on the envelope (schema v2) ([#77](https://github.com/Danube-Labs/javv-poc/issues/77)) ([8a2db1b](https://github.com/Danube-Labs/javv-poc/commit/8a2db1bebb31e96d3a9b520d1d090a74d933e59a)), closes [#23](https://github.com/Danube-Labs/javv-poc/issues/23)

## [0.1.1](https://github.com/Danube-Labs/javv-poc/compare/v0.1.0...v0.1.1) (2026-07-01)


### Bug Fixes

* **scanner:** isolate per-image scan failures + retrospective follow-ups ([#71](https://github.com/Danube-Labs/javv-poc/issues/71)) ([44d5072](https://github.com/Danube-Labs/javv-poc/commit/44d5072972db1743e7a6a0d276a417a22fdfde20))

## 0.1.0 (2026-06-30)


### Features

* M0 scanner package (discovery, adapters, normalize, envelope, push) ([#58](https://github.com/Danube-Labs/javv-poc/issues/58)) ([3f41eaf](https://github.com/Danube-Labs/javv-poc/commit/3f41eafdf42f11b679293b0bb2d1ed7be66ca425))
* M0b: scanner image publish + compatibility CI ([#63](https://github.com/Danube-Labs/javv-poc/issues/63)) ([f4002cf](https://github.com/Danube-Labs/javv-poc/commit/f4002cf710f89f49c5eb867b0d76386a86bee6d3))


### Bug Fixes

* correct tool-version probe (only kubectl/helm reject --version) ([#47](https://github.com/Danube-Labs/javv-poc/issues/47)) ([baa6422](https://github.com/Danube-Labs/javv-poc/commit/baa64227dc13488d1d0f13b989dd170c9f2ca603))
* setup-dev node install fails as root ($SUDO -E) ([cc34c17](https://github.com/Danube-Labs/javv-poc/commit/cc34c17f6828c73fea263b8be7efc13264ceb897))
