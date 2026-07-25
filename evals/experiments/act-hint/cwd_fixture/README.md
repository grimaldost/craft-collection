# Working directory

A neutral working directory for the act-hint detector's spawns. It is deliberately
empty of subject matter: no bank prompt's answer, no comparison, no numbers, and
nothing about how a response should be shaped. A spawn that reads its way around
this directory learns only that it is a scratch space.

It exists at all because a spawn with no working directory behaves differently from
one with a real repository under it, and because an empty temp directory differs
again. This fixture is the same for every arm and every prompt, so whatever it
contributes, it contributes equally.

Do not add material here. Anything a spawn could mistake for context is a side
channel to the ground truth.
