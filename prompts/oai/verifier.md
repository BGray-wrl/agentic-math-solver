I need you to check the following solution very carefully and let me know
if you find any gaps that cannot easily be fixed.
{% if check_refs %}You should also carefully check that all the
bibliographic references are valid.{% endif %}
# Problem
{{problem}}
# Solution?
{{solution}}
# Instructions
Something is considered a "gap" if it is a critical error that cannot
easily be fixed. If the proposed solution has no gaps, you should set
the "correct" key to true below and you provide an empty list "[]"
for the "gaps" key. If there are gaps, you should set the "correct"
key to false below and you should provide a list of gaps as specified.
Your output should be in the format:
<CORRECT>one of ’true’ or ’false’</CORRECT>
<GAPS>
[required section if correct is false]
- Brief explanation of gap_1
- Brief explanation of gap_2
- ...
</GAPS>