"""A Lab strategy on the Desk: the pieces that let tester code run on live prices.

SHADOW only (Step A): a promoted strategy runs in a sandboxed child, its orders become intents, the Desk's checks
(the door) say yes or no, and what would have filled is written down. Nothing in this package places an order or
talks to the desk process.
"""
