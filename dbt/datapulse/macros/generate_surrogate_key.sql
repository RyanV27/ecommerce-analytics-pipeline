{% macro generate_surrogate_key(field_list) %}
    to_hex(md5(concat(
        {% for field in field_list %}
            cast({{ field }} as string)
            {%- if not loop.last %}, '|', {% endif %}
        {% endfor %}
    )))
{% endmacro %}
