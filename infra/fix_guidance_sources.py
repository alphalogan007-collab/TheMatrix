import re

with open('/opt/mindai/docker-compose.topology.yml', 'r') as f:
    content = f.read()

# The GUIDANCE_SOURCES value is broken: starts with " but has no closing quote
# Use DOTALL to match across lines, stop at the next key or section
content = re.sub(
    r'(      GUIDANCE_SOURCES:).*?(?=\n      [A-Z_]|\n    volumes:)',
    r'\1 "/guidance/inbox"',
    content,
    flags=re.DOTALL
)

with open('/opt/mindai/docker-compose.topology.yml', 'w') as f:
    f.write(content)

print('Done')
broken = content.count('GUIDANCE_SOURCES: " /guidance/inbox')
fixed = [l for l in content.splitlines() if 'GUIDANCE_SOURCES' in l]
print(f'Remaining broken: {broken}')
print('All GUIDANCE_SOURCES lines:')
for l in fixed:
    print(repr(l))
