
def gen_utils():
    scales = [0, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 56, 64]
    
    output = []
    
    # Spacing
    for s in scales:
        s_str = str(s).replace('.', '_')
        val = f"{s*0.25}rem" if s != 0 else "0rem"
        output.append(f".f-p-{s_str} {{ padding: {val}; }}")
        output.append(f".f-px-{s_str} {{ padding-left: {val}; padding-right: {val}; }}")
        output.append(f".f-py-{s_str} {{ padding-top: {val}; padding-bottom: {val}; }}")
        output.append(f".f-pt-{s_str} {{ padding-top: {val}; }}")
        output.append(f".f-pb-{s_str} {{ padding-bottom: {val}; }}")
        output.append(f".f-pl-{s_str} {{ padding-left: {val}; }}")
        output.append(f".f-pr-{s_str} {{ padding-right: {val}; }}")
        
        output.append(f".f-m-{s_str} {{ margin: {val}; }}")
        output.append(f".f-mx-{s_str} {{ margin-left: {val}; margin-right: {val}; }}")
        output.append(f".f-my-{s_str} {{ margin-top: {val}; margin-bottom: {val}; }}")
        output.append(f".f-mt-{s_str} {{ margin-top: {val}; }}")
        output.append(f".f-mb-{s_str} {{ margin-bottom: {val}; }}")
        output.append(f".f-ml-{s_str} {{ margin-left: {val}; }}")
        output.append(f".f-mr-{s_str} {{ margin-right: {val}; }}")
        output.append(f".f-gap-{s_str} {{ gap: {val}; }}")

    # Opacity
    for o in range(0, 101, 10):
        output.append(f".f-opacity-{o} {{ opacity: {o/100}; }}")

    # Flex / Alignment helpers (Missing ones)
    output.append(".f-items-start { align-items: flex-start; }")
    output.append(".f-items-center { align-items: center; }")
    output.append(".f-items-end { align-items: flex-end; }")
    output.append(".f-justify-start { justify-content: flex-start; }")
    output.append(".f-justify-center { justify-content: center; }")
    output.append(".f-justify-end { justify-content: flex-end; }")
    output.append(".f-justify-between { justify-content: space-between; }")
    
    # Cursor
    output.append(".f-pointer-events-none { pointer-events: none; }")
    output.append(".f-pointer-events-auto { pointer-events: auto; }")

    print("\n".join(output))

if __name__ == "__main__":
    gen_utils()
