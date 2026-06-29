# Operate the `acme/svc` project end-to-end

You're the maintainer of `acme/svc`. Using `gh`, drive the project through a full
lifecycle. Complete **all** of the following so the repo ends in the described state:

1. **Repo**: update the repo description to `coverage-edited`. Clone it locally.
2. **Labels**: create a label named `audit`.
3. **Issues**: open an issue titled `Coverage incident`, comment on it, add the
   `audit` label to it, then close it. The seeded `Track: project setup` issue
   should be **reopened** if you ever close it (leave it open).
4. **Pull request**: create a branch that adds a `subtract` function to `app.py`,
   open a PR titled `Add subtract`, review-approve it, and **merge** it.
5. **Release**: publish a release tagged `v9.9`.
6. **CI**: trigger the `build` workflow, wait for it to finish, download its
   artifact, and open an issue whose **title is the build code** found inside the
   artifact file.

You have `gh` and `git`. Work entirely through `gh`.
