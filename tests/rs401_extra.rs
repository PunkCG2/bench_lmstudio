
#[test]
fn suma_que_desborda_u32_es_stack_overflow_sin_panico() {
    let r = std::panic::catch_unwind(|| parse_save("version=2\nplayer=A\nitem=a:4294967295\nitem=a:1\n"));
    assert!(r.is_ok(), "panic por desbordamiento");
    assert_eq!(r.unwrap(), Err(SaveError::StackOverflow { item: "a".into() }));
}

#[test]
fn una_sola_linea_que_pasa_el_maximo_de_pila() {
    assert_eq!(
        parse_save("version=2\nplayer=A\nitem=arrow:100\n"),
        Err(SaveError::StackOverflow { item: "arrow".into() })
    );
    assert!(matches!(parse_save("version=2\nplayer=A\nitem=arrow:4294967296\n"), Err(SaveError::InvalidNumber { line: 3, .. })));
}

#[test]
fn numero_de_linea_correcto_con_comentarios_y_vacias_antes() {
    assert_eq!(
        parse_save("# a\n\n# b\nversion=2\n\nplayer=A\nzzz=1\n"),
        Err(SaveError::UnknownKey { line: 7, key: "zzz".into() })
    );
}

#[test]
fn salto_de_linea_windows() {
    let d = parse_save("version=2\r\nplayer=Ana\r\ngold=5\r\nitem=a:2\r\n").unwrap();
    assert_eq!(d.player, "Ana");
    assert_eq!(d.gold, 5);
    assert_eq!(d.items.get("a"), Some(&2));
}
